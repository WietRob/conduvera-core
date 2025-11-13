const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const si = require('systeminformation');
const portscanner = require('portscanner');
const crypto = require('crypto-js');
const log = require('electron-log');

log.transports.file.resolvePathFn = () => path.join(__dirname, 'matrix-os.log');
log.transports.file.level = 'debug';
log.transports.console.level = 'debug';
log.info('Main: Starting Matrix OS');

const terminals = {};
let mainWindow;

Menu.setApplicationMenu(null);

app.disableHardwareAcceleration();

function createWindow() {
    log.info('Main: Creating window');
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        frame: false,
        backgroundColor: '#000000',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: false,
            nodeIntegration: true,
            devTools: true
        }
    });

    mainWindow.loadFile('index.html').catch(err => {
        log.error('Main: Failed to load index.html:', err);
    });

    mainWindow.webContents.openDevTools();

    mainWindow.webContents.on('did-finish-load', () => {
        log.info('Main: Window content loaded');
    });

    mainWindow.webContents.on('render-process-gone', (event, details) => {
        log.error('Main: Renderer process crashed:', details);
    });

    mainWindow.on('close', () => {
        log.info('Main: Window close event triggered');
        Object.keys(terminals).forEach(id => {
            if (terminals[id]) {
                terminals[id].kill();
                delete terminals[id];
            }
        });
        mainWindow.destroy();
    });
}

app.whenReady().then(() => {
    log.info('Main: App is ready');
    createWindow();

    app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) {
            createWindow();
        }
    });
});

app.on('window-all-closed', () => {
    log.info('Main: All windows closed');
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// Terminal Management
ipcMain.handle('terminal-create', (event, id) => {
    log.info(`Creating terminal with ID: ${id}`);
    try {
        const shell = process.platform === 'win32' ? 'cmd.exe' : '/bin/bash';
        const shellProcess = spawn(shell, [], {
            stdio: ['pipe', 'pipe', 'pipe'],
            cwd: process.env.HOME,
            env: process.env
        });

        terminals[id] = shellProcess;

        shellProcess.stdout.on('data', data => {
            mainWindow.webContents.send('terminal-data-' + id, data.toString());
        });

        shellProcess.stderr.on('data', data => {
            mainWindow.webContents.send('terminal-data-' + id, data.toString());
        });

        shellProcess.on('exit', () => {
            delete terminals[id];
            log.info(`Terminal ${id} closed`);
        });

        return id;
    } catch (error) {
        log.error(`Failed to create terminal ${id}: ${error.message}`);
        throw new Error(`Failed to create terminal: ${error.message}`);
    }
});

ipcMain.handle('terminal-write', (event, id, data) => {
    if (terminals[id]) {
        terminals[id].stdin.write(data);
    } else {
        log.error(`Terminal ${id} not found`);
        throw new Error(`Terminal ${id} not found`);
    }
});

ipcMain.handle('terminal-resize', (event, id, cols, rows) => {
    if (terminals[id]) {
        log.info(`Resize requested for terminal ${id}: ${cols}x${rows}`);
    } else {
        log.error(`Terminal ${id} not found`);
        throw new Error(`Terminal ${id} not found`);
    }
});

ipcMain.handle('terminal-kill', (event, id) => {
    if (terminals[id]) {
        terminals[id].kill();
        delete terminals[id];
        log.info(`Terminal ${id} killed`);
    }
});

// Cursor CLI
ipcMain.handle('cursor-execute', async (event, command) => {
    log.info(`Executing cursor command: ${command}`);
    return new Promise((resolve, reject) => {
        const cursorProcess = spawn('python', ['matrix_os/cli.py', ...command.split(' ')], {
            shell: true,
            cwd: path.join(__dirname)
        });

        let output = '';
        let error = '';

        cursorProcess.stdout.on('data', data => {
            output += data.toString();
        });

        cursorProcess.stderr.on('data', data => {
            error += data.toString();
        });

        cursorProcess.on('close', code => {
            if (code !== 0) {
                log.error(`Cursor command failed with code ${code}: ${error}`);
                reject({ code, error });
            } else {
                log.info(`Cursor command output: ${output}`);
                resolve(output);
            }
        });
    });
});

// System Monitoring
ipcMain.handle('system-info', async () => {
    log.info('Fetching system info');
    try {
        const cpu = await si.cpu();
        const mem = await si.mem();
        const disk = await si.fsSize();
        return {
            cpu: {
                brand: cpu.brand,
                cores: cpu.cores,
                speed: cpu.speed,
                usage: await si.currentLoad()
            },
            memory: {
                used: mem.used,
                total: mem.total
            },
            disk: disk
        };
    } catch (error) {
        log.error('Failed to fetch system info:', error);
        throw error;
    }
});

// Port Scan
ipcMain.handle('port-scan', async (event, host, startPort, endPort) => {
    log.info(`Starting port scan: ${host}, ports ${startPort}-${endPort}`);
    const openPorts = [];

    for (let port = startPort; port <= endPort; port++) {
        try {
            const status = await portscanner.checkPortStatus(port, host, { timeout: 1000 });
            if (status === 'open') {
                openPorts.push({
                    port,
                    service: getServiceName(port),
                    status: 'open'
                });
            }
            mainWindow.webContents.send('scan-progress', {
                current: port,
                total: endPort - startPort + 1,
                found: openPorts.length
            });
        } catch (error) {
            log.warn(`Error scanning port ${port}: ${error.message}`);
        }
    }

    log.info(`Port scan completed, found ${openPorts.length} open ports`);
    return openPorts;
});

function getServiceName(port) {
    const services = {
        20: 'FTP-DATA', 21: 'FTP', 22: 'SSH', 23: 'TELNET', 25: 'SMTP',
        80: 'HTTP', 110: 'POP3', 143: 'IMAP', 443: 'HTTPS', 3389: 'RDP'
    };
    return services[port] || 'UNKNOWN';
}

// Encryption/Decryption
ipcMain.handle('encrypt', async (event, text, password) => {
    log.info('Encrypting text');
    return crypto.AES.encrypt(text, password).toString();
});

ipcMain.handle('decrypt', async (event, encrypted, password) => {
    log.info('Decrypting text');
    try {
        const bytes = crypto.AES.decrypt(encrypted, password);
        return bytes.toString(crypto.enc.Utf8);
    } catch (error) {
        log.error('Decryption failed:', error);
        throw new Error('Decryption failed - wrong password?');
    }
});

// Hashing
ipcMain.handle('hash', async (event, text, algorithm) => {
    log.info(`Hashing text with ${algorithm}`);
    switch (algorithm) {
        case 'sha256':
            return crypto.SHA256(text).toString();
        case 'md5':
            return crypto.MD5(text).toString();
        default:
            return crypto.SHA256(text).toString();
    }
});

// Window Controls
ipcMain.handle('window-minimize', () => {
    log.info('Minimizing window');
    mainWindow.minimize();
});

ipcMain.handle('window-maximize', () => {
    log.info('Toggling maximize window');
    if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
    } else {
        mainWindow.maximize();
    }
});

ipcMain.handle('window-close', () => {
    log.info('Closing window');
    app.quit();
});

// Renderer Log
ipcMain.on('renderer-log', (event, message) => {
    console.log('Renderer: ' + message);
    log.info('Renderer: ' + message);
});