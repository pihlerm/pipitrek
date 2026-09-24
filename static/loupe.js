
import { parseRA, parseDec, printRA, printDEC } from './conversions.js';

const mainCanvas = document.getElementById('canvas');
const loupe = document.getElementById('loupe');
const loupeCtx = loupe.getContext('2d');
var loupeScale = 3; // Magnification factor
var loupeX = 0;
var loupeY = 0;

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
    const currentRa = (raCenter + raOffsetHours + 24) % 24;
    const currentDec = Math.max(-90, Math.min(90, decCenter + decOffsetDegrees));

    return { ra: currentRa, dec: currentDec };
}

function formatLoupeCoordinates() {
    const coordinates = getLoupeCoordinates();
    if (coordinates === null) {
        return 'RA --:--:--  DEC --*--:--';
    }

    return `RA ${printRA(coordinates.ra)}  ` + `DEC ${printDEC(coordinates.dec)}`;
}


export function updateLoupe() {

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

    loupeCtx.fillStyle = 'rgba(0, 0, 0, 0.7)';
    loupeCtx.fillRect(0, 0, loupe.width, 22);
    loupeCtx.fillStyle = '#00ff00';
    loupeCtx.font = '13px monospace';
    loupeCtx.textBaseline = 'top';
    loupeCtx.fillText(formatLoupeCoordinates(), 4, 4);
}

mainCanvas.addEventListener('mousemove', function (event) {
    
    // Position the loupe near the cursor
    loupe.style.left = `${event.clientX + 10}px`;
    loupe.style.top = `${event.clientY -20}px`;
    loupe.style.display = 'block';
    // Get the bounding rectangle of the canvas
    const rect = mainCanvas.getBoundingClientRect();

    // Calculate the mouse position relative to the canvas
    loupeX = event.clientX - rect.left;
    loupeY = event.clientY - rect.top;
    updateLoupe();

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