
const mainCanvas = document.getElementById('overlayCanvas');
const loupe = document.getElementById('loupe');
const loupeCtx = loupe.getContext('2d');
var loupeScale = 3; // Magnification factor
var loupeX = 0;
var loupeY = 0;
let loupeSearchMessages = [];
let loupeSearchRequest = 0;
const loupeSearchRadiusDeg = 0.01;

function getLoupeCoordinates() {
    const raText = document.getElementById('ra_current')?.textContent.trim();
    const decText = document.getElementById('dec_current')?.textContent.trim();
    const pixelScale = Number.parseFloat(document.getElementById('pixel_scale')?.value);
    const rotationAngle = Number.parseFloat(document.getElementById('rotation_angle')?.value) || 0;

    const raCenter = parseRA(raText);
    const decCenter = parseDec(decText);
    if (!Number.isFinite(raCenter) || !Number.isFinite(decCenter) || !Number.isFinite(pixelScale)) {
        return null;
    }

    const feedX = loupeX * full_feed_canvas.width / mainCanvas.width;
    const feedY = loupeY * full_feed_canvas.height / mainCanvas.height;
    const dx = feedX - full_feed_canvas.width / 2;
    const dy = feedY - full_feed_canvas.height / 2;
    const angle = rotationAngle * Math.PI / 180;
    const raPixels = dx * Math.cos(angle) - dy * Math.sin(angle);
    const decPixels = dx * Math.sin(angle) + dy * Math.cos(angle);
    const cosDec = Math.cos(decCenter * Math.PI / 180);
    const raOffsetHours = raPixels * pixelScale / Math.max(Math.abs(cosDec), 1e-6) / 54000;
    const decOffsetDegrees = decPixels * pixelScale / 3600;
    const currentRa = (raCenter - raOffsetHours + 24) % 24;
    const currentDec = Math.max(-90, Math.min(90, decCenter - decOffsetDegrees));

    return { ra: currentRa, dec: currentDec };
}

function formatLoupeCoordinates() {
    const coordinates = getLoupeCoordinates();
    if (coordinates === null) {
        return 'RA --:--:--  DEC --*--:--';
    }

    return `RA ${printRA(coordinates.ra)}  ` + `DEC ${printDEC(coordinates.dec)}`;
}

function parseCatalogDec(decText) {
    const match = /^([+-])(\d+)\*(\d+):(\d+(?:\.\d+)?)$/.exec(decText.trim());
    if (!match) return NaN;

    const sign = match[1] === '-' ? -1 : 1;
    return sign * (Number(match[2]) + Number(match[3]) / 60 + Number(match[4]) / 3600);
}

function angularSeparationDeg(ra1Deg, dec1Deg, ra2Deg, dec2Deg) {
    const radians = Math.PI / 180;
    const deltaRa = (ra2Deg - ra1Deg) * radians;
    const deltaDec = (dec2Deg - dec1Deg) * radians;
    const dec1Rad = dec1Deg * radians;
    const dec2Rad = dec2Deg * radians;
    const haversine = Math.sin(deltaDec / 2) ** 2 +
        Math.cos(dec1Rad) * Math.cos(dec2Rad) * Math.sin(deltaRa / 2) ** 2;

    return 2 * Math.asin(Math.sqrt(Math.min(1, haversine))) / radians;
}

function findInternalLoupeObject(coordinates) {
    const catalogs = [];
    if (typeof starCatalog !== 'undefined') catalogs.push({ entries: starCatalog, kind: 'star' });
    if (typeof ngcCatalog !== 'undefined') catalogs.push({ entries: ngcCatalog, kind: 'deep-sky' });

    const targetRaDeg = coordinates.ra * 15;
    const candidates = [];

    for (const catalog of catalogs) {
        for (const entry of catalog.entries) {
            const raHours = parseRA(entry[0]);
            const decDeg = parseCatalogDec(entry[1]);
            if (!Number.isFinite(raHours) || !Number.isFinite(decDeg)) continue;

            const separationDeg = angularSeparationDeg(
                targetRaDeg,
                coordinates.dec,
                raHours * 15,
                decDeg
            );
            const angularSizeArcmin = Number(entry[5]) || 0;
            const matchRadiusDeg = (32 + Math.max(0, angularSizeArcmin) * 60) / 3600;
            if (separationDeg <= matchRadiusDeg) {
                candidates.push({ entry, kind: catalog.kind, separationDeg });
            }
        }
    }

    candidates.sort((first, second) => first.separationDeg - second.separationDeg);
    return candidates.slice(0, 2);
}

function formatInternalLoupeObject(match) {
    const { entry, kind } = match;
    const identifiers = [entry[8], entry[7], entry[9] ? `M${entry[9]}` : '']
        .map(identifier => String(identifier || '').trim())
        .filter((identifier, index, all) => identifier && all.indexOf(identifier) === index);
    const label = identifiers.join(' / ') || 'Uncatalogued object';

    return kind === 'star' ? `Internal star: ${label}` : `Internal ${entry[2]}: ${label}`;
}

function formatSimbadLoupeObject(source) {
    const identifier = source.data.main_id || source.data.MAIN_ID || 'SIMBAD object';
    const objectType = source.data.otype_label || source.data.otype || '';
    return objectType ? `${identifier} (${objectType})` : identifier;
}

function searchLoupeObject() {
    const requestId = ++loupeSearchRequest;
    const coordinates = getLoupeCoordinates();
    if (coordinates === null) {
        loupeSearchMessages = ['Coordinates unavailable'];
        updateLoupe();
        return;
    }

    const internalMatches = findInternalLoupeObject(coordinates);
    const resultMessages = internalMatches.map(formatInternalLoupeObject);
    const remainingResults = 2 - resultMessages.length;
    if (remainingResults === 0) {
        loupeSearchMessages = resultMessages;
        updateLoupe();
        return;
    }

    if (!window.A || typeof A.catalogFromSimbad !== 'function') {
        resultMessages.push('SIMBAD search unavailable');
        loupeSearchMessages = resultMessages;
        updateLoupe();
        return;
    }

    loupeSearchMessages = [...resultMessages, 'Searching SIMBAD...'];
    updateLoupe();

    A.catalogFromSimbad(
        { ra: coordinates.ra * 15, dec: coordinates.dec },
        loupeSearchRadiusDeg,
        { limit: 10, orderBy: 'distance', orderDir: 'ASC' },
        catalog => {
            if (requestId !== loupeSearchRequest) return;

            const internalPositions = internalMatches.map(match => ({
                ra: parseRA(match.entry[0]) * 15,
                dec: parseCatalogDec(match.entry[1])
            }));
            const simbadMatches = catalog.getSources()
                .map(source => ({
                    source,
                    separationDeg: angularSeparationDeg(
                        coordinates.ra * 15,
                        coordinates.dec,
                        source.ra,
                        source.dec
                    )
                }))
                .filter(match => Number.isFinite(match.separationDeg) &&
                    !internalPositions.some(position =>
                        angularSeparationDeg(position.ra, position.dec, match.source.ra, match.source.dec) <= 1 / 3600))
                .sort((first, second) => first.separationDeg - second.separationDeg)
                .slice(0, remainingResults);

            resultMessages.push(...simbadMatches.map(match => formatSimbadLoupeObject(match.source)));
            while (resultMessages.length < 2) {
                resultMessages.push(resultMessages.length
                    ? 'No second object within 36 arcsec'
                    : 'No object within 36 arcsec');
            }
            loupeSearchMessages = resultMessages;
            updateLoupe();
        },
        error => {
            if (requestId !== loupeSearchRequest) return;
            console.error('SIMBAD loupe search failed:', error);
            resultMessages.push('SIMBAD search failed');
            loupeSearchMessages = resultMessages;
            updateLoupe();
        }
    );
}


function updateLoupe() {

    // Clear the loupe canvas
    loupeCtx.clearRect(0, 0, loupe.width, loupe.height);

    // Draw a portion of the video feed onto the loupe
    const loupeSizeW = loupe.width;
    const loupeSizeH = loupe.height;
    loupeCtx.imageSmoothingEnabled = false;
    
    const X = loupeX * full_feed_canvas.width / mainCanvas.width;
    const Y = loupeY * full_feed_canvas.height / mainCanvas.height;

    loupeCtx.drawImage(
        full_feed_canvas,
        X - loupeSizeW / (2 * loupeScale), // Source X
        Y - loupeSizeH / (2 * loupeScale), // Source Y
        loupeSizeW / loupeScale, // Source width
        loupeSizeH / loupeScale, // Source height
        0, // Destination X
        0, // Destination Y
        loupeSizeW, // Destination width
        loupeSizeH // Destination height
    );

    loupeCtx.strokeStyle = 'rgba(0, 255, 0, 0.8)';
    loupeCtx.lineWidth = 1;
    const centerX = loupeSizeW / 2;
    const centerY = loupeSizeH / 2;
    const centerRadius = 12;
    const crosshairGap = centerRadius + loupeCtx.lineWidth;
    loupeCtx.beginPath();
    loupeCtx.moveTo(centerX, 0);
    loupeCtx.lineTo(centerX, centerY - crosshairGap);
    loupeCtx.moveTo(centerX, centerY + crosshairGap);
    loupeCtx.lineTo(centerX, loupeSizeH);
    loupeCtx.moveTo(0, centerY);
    loupeCtx.lineTo(centerX - crosshairGap, centerY);
    loupeCtx.moveTo(centerX + crosshairGap, centerY);
    loupeCtx.lineTo(loupeSizeW, centerY);
    loupeCtx.stroke();
    loupeCtx.beginPath();
    loupeCtx.arc(centerX, centerY, centerRadius, 0, 2 * Math.PI);
    loupeCtx.stroke();

    loupeCtx.fillStyle = '#00ff00';
    loupeCtx.font = '13px monospace';
    loupeCtx.textBaseline = 'top';
    loupeCtx.lineWidth = 2;
    loupeCtx.lineJoin = 'round';
    loupeCtx.strokeStyle = 'rgba(0, 0, 0, 0.9)';
    const drawLoupeText = (text, y) => {
        loupeCtx.strokeText(text, 4, y, loupe.width - 8);
        loupeCtx.fillText(text, 4, y, loupe.width - 8);
    };
    drawLoupeText(formatLoupeCoordinates(), 4);
    loupeSearchMessages.slice(0, 2).forEach((message, index) => {
        drawLoupeText(message, 22 + index * 18);
    });
}

mainCanvas.addEventListener('mousemove', function (event) {
    
    // Position the loupe near the cursor
    loupe.style.left = `${event.clientX + 10}px`;
    loupe.style.top = `${event.clientY -20}px`;
    loupe.style.display = 'block';
    // Get the bounding rectangle of the canvas
    const rect = mainCanvas.getBoundingClientRect();

    // Calculate the mouse position relative to the canvas
    // with offset to the center of loupe icon
    loupeX = event.clientX - rect.left;
    loupeY = event.clientY - rect.top;
    loupeSearchRequest++;
    loupeSearchMessages = [];
    updateLoupe();

});

mainCanvas.addEventListener('click', function (event) {

    searchLoupeObject();
    const coordinates = getLoupeCoordinates();
    if (coordinates === null) return;

    const raInput = document.getElementById('ra-input');
    const decInput = document.getElementById('dec-input');
    if (raInput) raInput.value = formatRAFromDeg(coordinates.ra*15);
    if (decInput) decInput.value = formatDecFromDeg(coordinates.dec);
});

mainCanvas.addEventListener('mouseleave', function () {
    loupe.style.display = 'none'; // Hide the loupe when the mouse leaves the video feed
});

mainCanvas.addEventListener('wheel', function (event) {
    event.preventDefault(); // Prevent the page from scrolling

    // Adjust the scale based on the wheel delta
    if (event.deltaY < 0) {
        loupeScale = Math.min(loupeScale*1.4, 20);
    } else {
        loupeScale = Math.max(loupeScale/1.4, 1);
    }

    updateLoupe(); // Update the loupe with the new magnification
});