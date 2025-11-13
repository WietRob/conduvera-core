const { app, BrowserWindow, ipcMain, Menu } = require('electron');
const path = require('path');
const si = require('systeminformation');
const portscanner = require('portscanner');
const crypto = require('crypto-js');

let mainWindow;
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
    mainWindow.webContents.openDevTools(); // Debug Console öffnen
}

app.whenReady().then(createWindow);

app.on('window-all-closed', () => {
    if (process.platform !== 'darwin') app.quit();
});

// Dummy Terminal handlers
ipcMain.handle('terminal-create', async () => 'terminal-disabled');
ipcMain.handle('terminal-write', async () => {});
ipcMain.handle('terminal-resize', async () => {});
ipcMain.handle('terminal-kill', async () => {});
ipcMain.handle('terminal-data', async () => {});

// System Info - FUNKTIONIERT
ipcMain.handle('system-info', async () => {
    try {
        const cpu = await si.cpu();
        const mem = await si.mem();
        const load = await si.currentLoad();
        
        return {
            cpu: {
                brand: cpu.brand,
                cores: cpu.cores,
                speed: cpu.speed,
                usage: load
            },
            memory: {
                total: mem.total,
                free: mem.free,
                used: mem.used,
                available: mem.available
            },
            disk: [],
            network: [],
            processes: []
        };
    } catch (error) {
        console.error('System info error:', error);
        return {
            cpu: { brand: 'Unknown', cores: 0, speed: 0, usage: { currentLoad: 0 } },
            memory: { total: 0, free: 0, used: 0, available: 0 },
            disk: [],
            network: [],
            processes: []
        };
    }
});

// Port Scanner - FUNKTIONIERT
ipcMain.handle('port-scan', async (event, host, startPort, endPort) => {
    const openPorts = [];
    for (let port = startPort; port <= endPort && port <= startPort + 100; port++) {
        try {
            const status = await portscanner.checkPortStatus(port, host);
            if (status === 'open') {
                openPorts.push({ port, service: 'OPEN', status: 'open' });
            }
        } catch (error) {
            console.error(`Port ${port} error:`, error);
        }
    }
    return openPorts;
});

// Crypto - FUNKTIONIERT
ipcMain.handle('encrypt', async (event, text, password) => {
    return crypto.AES.encrypt(text, password).toString();
});

ipcMain.handle('decrypt', async (event, text, password) => {
    try {
        const bytes = crypto.AES.decrypt(text, password);
        return bytes.toString(crypto.enc.Utf8);
    } catch (error) {
        throw new Error('Decryption failed');
    }
});

ipcMain.handle('hash', async (event, text, algorithm) => {
    const algos = {
        'md5': crypto.MD5,
        'sha1': crypto.SHA1,
        'sha256': crypto.SHA256,
        'sha512': crypto.SHA512
    };
    return (algos[algorithm] || crypto.SHA256)(text).toString();
});

// Window Controls
ipcMain.handle('window-minimize', () => mainWindow.minimize());
ipcMain.handle('window-maximize', () => {
    if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
    } else {
        mainWindow.maximize();
    }
});
ipcMain.handle('window-close', () => app.quit());

// Stubs für andere Features
ipcMain.handle('cursor-execute', async () => 'Cursor CLI requires terminal - please install Build Tools');
ipcMain.handle('git-execute', async () => 'Git requires terminal');
ipcMain.handle('read-file', async () => '');
ipcMain.handle('write-file', async () => true);
ipcMain.handle('list-directory', async () => []);
ipcMain.handle('claude-api', async () => 'Claude API not configured');

console.log('Matrix OS started without terminal support');
