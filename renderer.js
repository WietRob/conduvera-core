console.log('Renderer: Script loaded');
window.electronAPI = require('electron').ipcRenderer;

document.addEventListener('DOMContentLoaded', () => {
    console.log('Renderer: DOM fully loaded');
    window.electronAPI.send('renderer-log', 'DOM fully loaded');

    const debugPanel = document.getElementById('debug-panel');
    if (!debugPanel) {
        console.error('Renderer: Debug panel not found');
        window.electronAPI.send('renderer-log', 'Error: Debug panel not found');
        return;
    }
    debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Renderer initialized`;
    window.electronAPI.send('renderer-log', 'Renderer initialized');

    // Matrix-Regen
    try {
        const canvas = document.getElementById('matrix-canvas');
        if (canvas) {
            canvas.width = window.innerWidth;
            canvas.height = window.innerHeight;
            const ctx = canvas.getContext('2d');
            if (!ctx) {
                throw new Error('Canvas context not available');
            }
            const chars = '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ';
            const fontSize = 14;
            const columns = canvas.width / fontSize;
            const drops = Array(Math.floor(columns)).fill(0);

            function drawMatrix() {
                ctx.fillStyle = 'rgba(0, 0, 0, 0.05)';
                ctx.fillRect(0, 0, canvas.width, canvas.height);
                ctx.fillStyle = '#00ff00';
                ctx.font = `${fontSize}px monospace`;

                for (let i = 0; i < drops.length; i++) {
                    const text = chars.charAt(Math.floor(Math.random() * chars.length));
                    const x = i * fontSize;
                    const y = drops[i] * fontSize;
                    ctx.fillText(text, x, y);
                    if (y > canvas.height && Math.random() > 0.975) drops[i] = 0;
                    drops[i]++;
                }
            }

            setInterval(drawMatrix, 33);
            console.log('Renderer: Matrix Regen initialized');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Matrix Regen initialized`;
            window.electronAPI.send('renderer-log', 'Matrix Regen initialized');
        } else {
            console.error('Renderer: Canvas not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Canvas not found`;
            window.electronAPI.send('renderer-log', 'Error: Canvas not found');
        }
    } catch (error) {
        console.error('Renderer: Matrix Regen setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Matrix Regen setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Matrix Regen setup failed: ${error.message}`);
    }

    // Xterm-Terminal
    try {
        console.log('Renderer: Attempting to load Xterm module');
        window.electronAPI.send('renderer-log', 'Attempting to load Xterm module');
        const { Terminal } = require('@xterm/xterm');
        console.log('Renderer: Xterm module loaded');
        window.electronAPI.send('renderer-log', 'Xterm module loaded');
        const term = new Terminal({
            cursorBlink: true,
            theme: { background: '#000000', foreground: '#00ff00' }
        });
        const terminalElement = document.getElementById('terminal');
        if (terminalElement) {
            const termId = 'terminal-' + Date.now();
            term.open(terminalElement);
            window.electronAPI.invoke('terminal-create', termId).then(() => {
                term.write('Matrix OS Terminal\n$ ');
                term.onData(data => {
                    window.electronAPI.invoke('terminal-write', termId, data);
                    if (data === '\r') term.write('\n$ ');
                });
                window.electronAPI.on('terminal-data-' + termId, (event, data) => {
                    term.write(data);
                });
            }).catch(error => {
                console.error('Renderer: Terminal creation failed:', error);
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Terminal creation failed: ${error.message}`;
                window.electronAPI.send('renderer-log', `Error: Terminal creation failed: ${error.message}`);
            });
            console.log('Renderer: Xterm initialized');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Xterm initialized`;
            window.electronAPI.send('renderer-log', 'Xterm initialized');
        } else {
            console.error('Renderer: Terminal element not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Terminal element not found`;
            window.electronAPI.send('renderer-log', 'Error: Terminal element not found');
        }
    } catch (error) {
        console.error('Renderer: Xterm initialization failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Xterm initialization failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Xterm initialization failed: ${error.message}`);
    }

    // Window Creation Functions
    function createWindow(id, title, content) {
        let win = document.getElementById(id);
        if (win) {
            win.style.display = 'block';
            return win;
        }

        win = document.createElement('div');
        win.id = id;
        win.className = 'window';
        win.style.top = '100px';
        win.style.left = '100px';
        win.innerHTML = `
            <div class="window-header">
                <span>${title}</span>
                <button onclick="document.getElementById('${id}').style.display='none'">X</button>
            </div>
            <div class="window-content">${content}</div>
        `;
        document.body.appendChild(win);
        makeDraggable(win);
        return win;
    }

    function makeDraggable(element) {
        let isDragging = false;
        let currentX, currentY, initialX, initialY;

        element.querySelector('.window-header').addEventListener('mousedown', (e) => {
            initialX = e.clientX - currentX;
            initialY = e.clientY - currentY;
            isDragging = true;
        });

        document.addEventListener('mousemove', (e) => {
            if (isDragging) {
                e.preventDefault();
                currentX = e.clientX - initialX;
                currentY = e.clientY - initialY;
                element.style.left = currentX + 'px';
                element.style.top = currentY + 'px';
            }
        });

        document.addEventListener('mouseup', () => {
            isDragging = false;
        });

        currentX = parseInt(element.style.left) || 100;
        currentY = parseInt(element.style.top) || 100;
    }

    // Terminal Button
    try {
        const terminalButton = document.getElementById('terminal-button');
        if (terminalButton) {
            terminalButton.addEventListener('click', () => {
                console.log('Renderer: Terminal button clicked');
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Terminal button clicked`;
                window.electronAPI.send('renderer-log', 'Terminal button clicked');
                document.getElementById('terminal').style.display = 'block';
            });
        } else {
            console.error('Renderer: Terminal button not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Terminal button not found`;
            window.electronAPI.send('renderer-log', 'Error: Terminal button not found');
        }
    } catch (error) {
        console.error('Renderer: Terminal button setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Terminal button setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Terminal button setup failed: ${error.message}`);
    }

    // Cursor CLI Window
    try {
        const cursorButton = document.getElementById('cursor-button');
        if (cursorButton) {
            cursorButton.addEventListener('click', () => {
                console.log('Renderer: Cursor button clicked');
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Cursor button clicked`;
                window.electronAPI.send('renderer-log', 'Cursor button clicked');
                const win = createWindow('cursor-window', 'Cursor CLI', `
                    <input id="cursor-command" type="text" placeholder="Enter command (e.g., status)">
                    <button class="cursor-execute">Execute</button>
                    <button class="cursor-status">Status</button>
                    <button class="cursor-version">Version</button>
                    <textarea id="cursor-output" readonly></textarea>
                `);
                win.querySelector('.cursor-execute').addEventListener('click', executeCursor);
                win.querySelector('.cursor-status').addEventListener('click', () => cursorCmd('status'));
                win.querySelector('.cursor-version').addEventListener('click', () => cursorCmd('--version'));
            });
        } else {
            console.error('Renderer: Cursor button not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Cursor button not found`;
            window.electronAPI.send('renderer-log', 'Error: Cursor button not found');
        }
    } catch (error) {
        console.error('Renderer: Cursor button setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Cursor button setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Cursor button setup failed: ${error.message}`);
    }

    async function executeCursor() {
        const command = document.getElementById('cursor-command');
        const output = document.getElementById('cursor-output');
        if (!command || !output) return;

        if (!command.value) {
            output.textContent = 'Please enter a command';
            return;
        }

        output.innerHTML = '<span class="loading">Executing...</span>';

        try {
            const result = await window.electronAPI.invoke('cursor-execute', command.value);
            output.textContent = result;
        } catch (error) {
            output.textContent = 'Error: ' + (error.error || error.message);
        }
    }

    async function cursorCmd(cmd) {
        const command = document.getElementById('cursor-command');
        if (!command) return;
        command.value = cmd;
        await executeCursor();
    }

    // Crypto Window
    try {
        const cryptoButton = document.getElementById('crypto-button');
        if (cryptoButton) {
            cryptoButton.addEventListener('click', () => {
                console.log('Renderer: Crypto button clicked');
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Crypto button clicked`;
                window.electronAPI.send('renderer-log', 'Crypto button clicked');
                const win = createWindow('crypto-window', 'Crypto Tools', `
                    <input id="encrypt-text" type="text" placeholder="Text to encrypt/decrypt">
                    <input id="encrypt-password" type="password" placeholder="Password">
                    <button class="encrypt-btn">Encrypt</button>
                    <button class="decrypt-btn">Decrypt</button>
                    <textarea id="crypto-output" readonly></textarea>
                    <input id="hash-text" type="text" placeholder="Text to hash">
                    <button class="hash-sha256">SHA256</button>
                    <button class="hash-md5">MD5</button>
                    <textarea id="hash-output" readonly></textarea>
                `);
                win.querySelector('.encrypt-btn').addEventListener('click', encryptText);
                win.querySelector('.decrypt-btn').addEventListener('click', decryptText);
                win.querySelector('.hash-sha256').addEventListener('click', () => hashText('sha256'));
                win.querySelector('.hash-md5').addEventListener('click', () => hashText('md5'));
            });
        } else {
            console.error('Renderer: Crypto button not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Crypto button not found`;
            window.electronAPI.send('renderer-log', 'Error: Crypto button not found');
        }
    } catch (error) {
        console.error('Renderer: Crypto button setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Crypto button setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Crypto button setup failed: ${error.message}`);
    }

    async function encryptText() {
        const text = document.getElementById('encrypt-text');
        const password = document.getElementById('encrypt-password');
        const output = document.getElementById('crypto-output');
        if (!text || !password || !output) return;

        if (!text.value || !password.value) {
            output.textContent = 'Please enter text and password';
            return;
        }

        try {
            const encrypted = await window.electronAPI.invoke('encrypt', text.value, password.value);
            output.textContent = 'ENCRYPTED:\n' + encrypted;
        } catch (error) {
            output.textContent = 'Encryption failed: ' + error.message;
        }
    }

    async function decryptText() {
        const text = document.getElementById('encrypt-text');
        const password = document.getElementById('encrypt-password');
        const output = document.getElementById('crypto-output');
        if (!text || !password || !output) return;

        if (!text.value || !password.value) {
            output.textContent = 'Please enter encrypted text and password';
            return;
        }

        try {
            const decrypted = await window.electronAPI.invoke('decrypt', text.value, password.value);
            output.textContent = 'DECRYPTED:\n' + decrypted;
        } catch (error) {
            output.textContent = 'Decryption failed: ' + error.message;
        }
    }

    async function hashText(algorithm) {
        const text = document.getElementById('hash-text');
        const output = document.getElementById('hash-output');
        if (!text || !output) return;

        if (!text.value) {
            output.textContent = 'Please enter text to hash';
            return;
        }

        try {
            const hash = await window.electronAPI.invoke('hash', text.value, algorithm);
            output.textContent = algorithm.toUpperCase() + ':\n' + hash;
        } catch (error) {
            output.textContent = 'Hashing failed: ' + error.message;
        }
    }

    // Network Window
    try {
        const networkButton = document.getElementById('network-button');
        if (networkButton) {
            networkButton.addEventListener('click', () => {
                console.log('Renderer: Network button clicked');
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Network button clicked`;
                window.electronAPI.send('renderer-log', 'Network button clicked');
                const win = createWindow('network-window', 'Network Tools', `
                    <input id="scan-host" type="text" placeholder="Host (e.g., localhost)">
                    <input id="scan-start" type="number" placeholder="Start Port" value="1">
                    <input id="scan-end" type="number" placeholder="End Port" value="1000">
                    <button class="scan-btn">Scan</button>
                    <textarea id="scan-output" readonly></textarea>
                `);
                win.querySelector('.scan-btn').addEventListener('click', startPortScan);
            });
        } else {
            console.error('Renderer: Network button not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Network button not found`;
            window.electronAPI.send('renderer-log', 'Error: Network button not found');
        }
    } catch (error) {
        console.error('Renderer: Network button setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Network button setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Network button setup failed: ${error.message}`);
    }

    async function startPortScan() {
        const host = document.getElementById('scan-host');
        const start = document.getElementById('scan-start');
        const end = document.getElementById('scan-end');
        const output = document.getElementById('scan-output');
        if (!host || !start || !end || !output) return;

        if (!host.value || isNaN(start.value) || isNaN(end.value)) {
            output.textContent = 'Please enter valid host and port range';
            return;
        }

        output.innerHTML = '<span class="loading">Scanning...</span>';

        try {
            const results = await window.electronAPI.invoke('port-scan', host.value, parseInt(start.value), parseInt(end.value));
            let html = 'SCAN RESULTS:\n\n';
            results.forEach(port => {
                html += `Port ${port.port} (${port.service}): OPEN\n`;
            });
            output.textContent = html || 'No open ports found';
        } catch (error) {
            output.textContent = 'Scan failed: ' + error.message;
        }

        window.electronAPI.on('scan-progress', (event, data) => {
            output.textContent = `Scanning port ${data.current}/${data.total}... Found ${data.found} open ports`;
        });
    }

    // Hacking Window
    try {
        const hackingButton = document.getElementById('hacking-button');
        if (hackingButton) {
            hackingButton.addEventListener('click', () => {
                console.log('Renderer: Hacking button clicked');
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Hacking button clicked`;
                window.electronAPI.send('renderer-log', 'Hacking button clicked');
                const win = createWindow('hacking-window', 'Ethical Hacking', `
                    <input id="hack-host" type="text" placeholder="Host (e.g., localhost)">
                    <button class="hack-btn">Scan</button>
                    <textarea id="hacking-output" readonly></textarea>
                `);
                win.querySelector('.hack-btn').addEventListener('click', startVulnerabilityScan);
            });
        } else {
            console.error('Renderer: Hacking button not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Hacking button not found`;
            window.electronAPI.send('renderer-log', 'Error: Hacking button not found');
        }
    } catch (error) {
        console.error('Renderer: Hacking button setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Hacking button setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Hacking button setup failed: ${error.message}`);
    }

    async function startVulnerabilityScan() {
        const host = document.getElementById('hack-host');
        const output = document.getElementById('hacking-output');
        if (!host || !output) return;

        if (!host.value) {
            output.textContent = 'Please enter a host';
            return;
        }

        output.innerHTML = '<span class="loading">Scanning...</span>';

        try {
            const openPorts = await window.electronAPI.invoke('port-scan', host.value, 1, 1000);
            let report = 'VULNERABILITY REPORT:\n\n';
            openPorts.forEach(port => {
                report += `Open port ${port.port} (${port.service}): Potential vulnerability if not intended\n`;
            });
            output.textContent = report || 'No vulnerabilities found';
        } catch (error) {
            output.textContent = 'Scan failed: ' + error.message;
        }
    }

    // Monitoring Window
    try {
        const monitoringButton = document.getElementById('monitoring-button');
        if (monitoringButton) {
            monitoringButton.addEventListener('click', () => {
                console.log('Renderer: Monitoring button clicked');
                debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Monitoring button clicked`;
                window.electronAPI.send('renderer-log', 'Monitoring button clicked');
                const win = createWindow('monitoring-window', 'System Monitoring', `
                    <textarea id="monitoring-output" readonly></textarea>
                `);
                getSystemMonitoring();
                setInterval(getSystemMonitoring, 5000);
            });
        } else {
            console.error('Renderer: Monitoring button not found');
            debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Monitoring button not found`;
            window.electronAPI.send('renderer-log', 'Error: Monitoring button not found');
        }
    } catch (error) {
        console.error('Renderer: Monitoring button setup failed:', error);
        debugPanel.textContent += `\n[${new Date().toLocaleTimeString()}] Error: Monitoring button setup failed: ${error.message}`;
        window.electronAPI.send('renderer-log', `Error: Monitoring button setup failed: ${error.message}`);
    }

    async function getSystemMonitoring() {
        const output = document.getElementById('monitoring-output');
        if (!output) return;

        output.innerHTML = '<span class="loading">Monitoring...</span>';

        try {
            const info = await window.electronAPI.invoke('system-info');
            let html = 'SYSTEM MONITORING:\n\n';
            html += `CPU: ${info.cpu.brand} (${info.cpu.cores} cores, ${info.cpu.speed} GHz)\n`;
            html += `CPU Usage: ${info.cpu.usage.currentLoad.toFixed(1)}%\n`;
            html += `Memory: ${(info.memory.used / 1073741824).toFixed(2)} GB / ${(info.memory.total / 1073741824).toFixed(2)} GB\n`;
            html += `Disk: ${(info.disk[0].used / 1073741824).toFixed(2)} GB / ${(info.disk[0].size / 1073741824).toFixed(2)} GB\n`;
            output.textContent = html;
        } catch (error) {
            output.textContent = 'Monitoring failed: ' + error.message;
        }
    }
});