    
    async function dslrPost(url, body) {
        const response = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body || {})
        });
        return await response.json();
    }

    function dslrSetMessage(text) {
        document.getElementById('dslr_message').textContent = text;
    }

    function dslrSetStatus(mounted) {
        const el = document.getElementById('dslr_status');
        el.textContent = mounted ? 'Mounted' : 'Not mounted';
        el.style.color = mounted ? '#4caf50' : '#f44336';
    }

    function dslrSetTriggered(triggered) {
        const btn = document.getElementById('dslr_trigger_button');
        const abort = document.getElementById('dslr_abort_button');
        btn.classList.toggle('active', triggered);
        btn.disabled = triggered;
        btn.style.cursor = triggered ? 'not-allowed' : '';
        abort.style.display = triggered ? '' : 'none';
        document.querySelectorAll('.dslr-idle-only').forEach(b => {
            b.disabled = triggered;
            b.style.cursor = triggered ? 'not-allowed' : '';
        });
    }

    async function dslrProcessStatus(data) {
            dslrSetStatus(data.mounted);
            const cameraIndicator = document.getElementById('indicator-camera');
            
            cameraIndicator.classList.toggle('flash-green', data.triggered);
            dslrSetTriggered(!!data.triggered);
    }

    async function dslrAbort() {
        try {
            const data = await dslrPost('/dslr_trigger_abort');
            dslrSetMessage(data.message || 'Aborted');
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
        dslrCheckStatus();
    }

    async function dslrCheckStatus() {
        try {
            const data = await dslrPost('/dslr_get_state');
            dslrProcessStatus(data);
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
    }

    async function dslrMount() {
        dslrSetMessage('Mounting...');
        try {
            const data = await dslrPost('/dslr_mount',{mount: true});
            dslrSetMessage(data.message || '');
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
        dslrCheckStatus();
    }

    async function dslrUnmount() {
        dslrSetMessage('Unmounting...');
        try {
            const data = await dslrPost('/dslr_mount',{mount: false});
            dslrSetMessage(data.message || '');
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
        dslrCheckStatus();
    }

    async function dslrList() {
        dslrSetMessage('Reading image list...');
        const list = document.getElementById('dslr_image_list');
        try {
            const data = await dslrPost('/dslr_get_image_list');
            if (data.status !== 'success') {
                dslrSetMessage(data.message || 'Failed to list images');
                return;
            }
            const newImages = new Set(data.new_images || []);
            const localSet = new Set(data.local_images || []);
            const remoteSet = new Set(data.images);
            const names = Array.from(new Set([...localSet, ...remoteSet])).sort();
            list.innerHTML = '';
            const table = document.createElement('table');
            table.style.width = '100%';
            table.style.borderCollapse = 'collapse';
            const head = table.createTHead().insertRow();
            const thSel = document.createElement('th');
            const selAll = document.createElement('input');
            selAll.type = 'checkbox';
            selAll.title = 'Select/deselect all';
            selAll.onchange = () => table.querySelectorAll('input.dslr_sel').forEach(c => c.checked = selAll.checked);
            thSel.appendChild(selAll);
            head.appendChild(thSel);
            for (const title of ['Local', 'DSLR']) {
                const th = document.createElement('th');
                th.textContent = title;
                th.style.textAlign = 'left';
                th.style.padding = '2px 4px';
                head.appendChild(th);
            }
            const body = table.createTBody();
            const makeCell = (row, name, present) => {
                const td = row.insertCell();
                td.style.padding = '2px 4px';
                td.style.width = '50%';
                if (!present) return;
                td.textContent = name;
                td.style.cursor = 'pointer';
                if (present === 'new') td.style.color = '#ffc107';
                td.onclick = () => dslrShowImage(name);
            };
            for (const name of names) {
                const row = body.insertRow();
                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.className = 'dslr_sel';
                cb.value = name;
                row.insertCell().appendChild(cb);
                makeCell(row, name, localSet.has(name));
                makeCell(row, name, remoteSet.has(name) && (newImages.has(name) ? 'new' : true));
            }
            list.appendChild(table);
            dslrSetMessage(data.images.length + ' images, ' + newImages.size + ' new');
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
    }

    async function dslrDownloadRaw() {
        const images = Array.from(document.querySelectorAll('#dslr_image_list input.dslr_sel:checked')).map(c => c.value);
        if (!images.length) {
            dslrSetMessage('No images selected');
            return;
        }
        dslrSetMessage('Preparing ' + images.length + ' images...');
        try {
            const data = await dslrPost('/dslr_get_raw_images', { images });
            if (data.status !== 'success') {
                dslrSetMessage(data.message || 'Download failed');
                return;
            }
            const a = document.createElement('a');
            a.href = data.raw_images;
            a.download = '';
            document.body.appendChild(a);
            a.click();
            a.remove();
            dslrSetMessage('Downloading ' + images.length + ' images');
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
    }

    async function dslrSynchronize() {
        dslrSetMessage('Downloading new images...');
        try {
            const data = await dslrPost('/dslr_download_new_images');
            if (data.status !== 'success') {
                dslrSetMessage(data.message || 'Synchronize failed');
                return;
            }
            dslrSetMessage('Downloaded ' + data.downloaded.length + ' images');
            dslrList();
        } catch (e) {
            dslrSetMessage('Error: ' + e);
        }
    }

    async function dslrShowImage(name) {
        dslrSetMessage('Loading ' + name + '...');
        const win = window.open('', '_blank');
        try {
            const data = await dslrPost('/dslr_get_image', { filename: name });
            if (data.status !== 'success') {
                if (win) win.close();
                dslrSetMessage(data.message || 'Failed to load image (synchronize first?)');
                return;
            }
            if (!win) {
                dslrSetMessage('Popup blocked by the browser');
                return;
            }
            win.document.title = name;
            win.document.body.style.cssText = 'margin:0;background:#111;';
            const img = win.document.createElement('img');
            img.src = data.image;
            img.style.cssText = 'display:block;max-width:200%;margin:auto;';
            win.document.body.appendChild(img);
            dslrSetMessage('');
        } catch (e) {
            if (win) win.close();
            dslrSetMessage('Error: ' + e);
        }
    }

    async function dslrTrigger() {
        dslrSetMessage('Triggering...');
        try {
            const dur = document.getElementById('dslr_trigger_seconds').value;
            const cameraIndicator = document.getElementById('indicator-camera');          
            cameraIndicator.classList.toggle('flash-green', true);
            dslrSetTriggered(true);
            const data = await dslrPost('/dslr_trigger',{duration:dur, count:1});
            dslrSetMessage(data.message || '');
            if (data.status === 'error') dslrSetTriggered(false);
        } catch (e) {
            dslrSetMessage('Error: ' + e);
            dslrSetTriggered(false);
        }
    }

    
