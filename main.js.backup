const { app, BrowserWindow, ipcMain, Menu, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const pty = require('node-pty');
const si = require('systeminformation');
const portscanner = require('portscanner');
const crypto = require('crypto-js');
const fs = require('fs').promises;
const os = require('os');

// Terminal sessions storage
const terminals = {};
let mainWindow;

// Disable menu bar
Menu.setApplicationMenu(null);

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1400,
        height: 900,
        frame: false,
        backgroundColor: '#000000',
        webPreferences: {
            preload: path.join(__dirname, 'preload.js'),
            contextIsolation: true,
            nodeIntegration: false
        }
    });

    mainWindow.loadFile('index.html');
    
    // Enable DevTools in development
    if (process.env.NODE_ENV === 'development') {
        mainWindow.webContents.openDevTools();
    }
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') {
        app.quit();
    }
});

// === TERMINAL MANAGEMENT ===
ipcMain.handle('terminal-create', (event, id) => {
    const shell = process.platform === 'win32' ? 'powershell.exe' : 'bash';
    const ptyProcess = pty.spawn(shell, [], {
        name: 'xterm-color',
        cols: 80,
        rows: 30,
        cwd: process.env.HOME,
        env: process.env
    });

    terminals[id] = ptyProcess;

    ptyProcess.on('data', (data) => {
        mainWindow.webContents.send('terminal-data-' + id, data);
    });

    return id;
});

ipcMain.handle('terminal-write', (event, id, data) => {
    if (terminals[id]) {
        terminals[id].write(data);
    }
});

ipcMain.handle('terminal-resize', (event, id, cols, rows) => {
    if (terminals[id]) {
        terminals[id].resize(cols, rows);
    }
});

ipcMain.handle('terminal-kill', (event, id) => {
    if (terminals[id]) {
        terminals[id].kill();
        delete terminals[id];
    }
});

// === CURSOR CLI INTEGRATION ===
ipcMain.handle('cursor-execute', async (event, command) => {
    return new Promise((resolve, reject) => {
        const cursorProcess = spawn('cursor', command.split(' '), {
            shell: true,
            cwd: process.cwd()
        });

        let output = '';
        let error = '';

        cursorProcess.stdout.on('data', (data) => {
            output += data.toString();
        });

        cursorProcess.stderr.on('data', (data) => {
            error += data.toString();
        });

        cursorProcess.on('close', (code) => {
            if (code !== 0) {
                reject({ code, error });
            } else {
                resolve(output);
            }
        });
    });
});

// === SYSTEM MONITORING ===
ipcMain.handle('system-info', async () => {
    const cpu = await si.cpu();
    const mem = await si.mem();
    const disk = await si.fsSize();
    const network = await si.networkInterfaces();
    const processes = await si.processes();

    return {
        cpu: {
            manufacturer: cpu.manufacturer,
            brand: cpu.brand,
            speed: cpu.speed,
            cores: cpu.cores,
            usage: await si.currentLoad()
        },
        memory: {
            total: mem.total,
            free: mem.free,
            used: mem.used,
            active: mem.active,
            available: mem.available
        },
        disk: disk,
        network: network,
        processes: processes.list.slice(0, 10) // Top 10 processes
    };
});

// === NETWORK TOOLS ===
ipcMain.handle('port-scan', async (event, host, startPort, endPort) => {
    const openPorts = [];
    
    for (let port = startPort; port <= endPort; port++) {
        try {
            const status = await portscanner.checkPortStatus(port, host);
            if (status === 'open') {
                openPorts.push({
                    port,
                    service: getServiceName(port),
                    status: 'open'
                });
            }
            // Send progress
            mainWindow.webContents.send('scan-progress', {
                current: port,
                total: endPort - startPort,
                found: openPorts.length
            });
        } catch (error) {
            console.error(`Error scanning port ${port}: ${error}`);
        }
    }
    
    return openPorts;
});

function getServiceName(port) {
    const services = {
        20: 'FTP-DATA',
        21: 'FTP',
        22: 'SSH',
        23: 'TELNET',
        25: 'SMTP',
        53: 'DNS',
        80: 'HTTP',
        110: 'POP3',
        143: 'IMAP',
        443: 'HTTPS',
        445: 'SMB',
        3306: 'MySQL',
        3389: 'RDP',
        5432: 'PostgreSQL',
        5900: 'VNC',
        8080: 'HTTP-PROXY',
        8443: 'HTTPS-ALT',
        27017: 'MongoDB'
    };
    return services[port] || 'UNKNOWN';
}

// === ENCRYPTION TOOLS ===
ipcMain.handle('encrypt', async (event, text, password) => {
    return crypto.AES.encrypt(text, password).toString();
});

ipcMain.handle('decrypt', async (event, encrypted, password) => {
    try {
        const bytes = crypto.AES.decrypt(encrypted, password);
        return bytes.toString(crypto.enc.Utf8);
    } catch (error) {
        throw new Error('Decryption failed - wrong password?');
    }
});

ipcMain.handle('hash', async (event, text, algorithm) => {
    switch(algorithm) {
        case 'md5':
            return crypto.MD5(text).toString();
        case 'sha1':
            return crypto.SHA1(text).toString();
        case 'sha256':
            return crypto.SHA256(text).toString();
        case 'sha512':
            return crypto.SHA512(text).toString();
        default:
            return crypto.SHA256(text).toString();
    }
});

// === FILE OPERATIONS ===
ipcMain.handle('read-file', async (event, filepath) => {
    try {
        const content = await fs.readFile(filepath, 'utf8');
        return content;
    } catch (error) {
        throw new Error(`Failed to read file: ${error.message}`);
    }
});

ipcMain.handle('write-file', async (event, filepath, content) => {
    try {
        await fs.writeFile(filepath, content, 'utf8');
        return true;
    } catch (error) {
        throw new Error(`Failed to write file: ${error.message}`);
    }
});

ipcMain.handle('list-directory', async (event, dirpath) => {
    try {
        const files = await fs.readdir(dirpath, { withFileTypes: true });
        return files.map(file => ({
            name: file.name,
            isDirectory: file.isDirectory(),
            path: path.join(dirpath, file.name)
        }));
    } catch (error) {
        throw new Error(`Failed to list directory: ${error.message}`);
    }
});

// === GIT OPERATIONS ===
ipcMain.handle('git-execute', async (event, command) => {
    return new Promise((resolve, reject) => {
        const gitProcess = spawn('git', command.split(' '), {
            cwd: process.cwd()
        });

        let output = '';
        let error = '';

        gitProcess.stdout.on('data', (data) => {
            output += data.toString();
        });

        gitProcess.stderr.on('data', (data) => {
            error += data.toString();
        });

        gitProcess.on('close', (code) => {
            if (code !== 0) {
                reject({ code, error });
            } else {
                resolve(output);
            }
        });
    });
});

// === WINDOW CONTROLS ===
ipcMain.handle('window-minimize', () => {
    mainWindow.minimize();
});

ipcMain.handle('window-maximize', () => {
    if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
    } else {
        mainWindow.maximize();
    }
});

ipcMain.handle('window-close', () => {
    app.quit();
});

// === CLAUDE API ===
ipcMain.handle('claude-api', async (event, prompt, apiKey) => {
    const axios = require('axios');
    
    try {
        const response = await axios.post('https://api.anthropic.com/v1/messages', {
            model: 'claude-3-opus-20240229',
            max_tokens: 1000,
            messages: [
                { role: 'user', content: prompt }
            ]
        }, {
            headers: {
                'Content-Type': 'application/json',
                'x-api-key': apiKey,
                'anthropic-version': '2023-06-01'
            }
        });
        
        return response.data.content[0].text;
    } catch (error) {
        throw new Error(`Claude API Error: ${error.message}`);
    }
});