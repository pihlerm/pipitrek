
const videoFeed = document.getElementById('video_feed');
const threshFeed = document.getElementById('thresh_feed');
const mainCanvas = document.getElementById('canvas');
const loupe = document.getElementById('loupe');
const loupeCtx = loupe.getContext('2d');

function isVideoFeedHidden() {
    const style = window.getComputedStyle(videoFeed);
    return style.display === 'none' || style.visibility === 'hidden';
}

mainCanvas.addEventListener('mousemove', function (event) {
    
    const srcEl = isVideoFeedHidden() ? threshFeed : videoFeed;
    
    const rect = srcEl.getBoundingClientRect();
    const x = event.clientX - rect.left; // X relative to the video feed
    const y = event.clientY - rect.top;  // Y relative to the video feed

    // Position the loupe near the cursor
    loupe.style.left = `${event.clientX + 10}px`;
    loupe.style.top = `${event.clientY + 10}px`;
    loupe.style.display = 'block';

    // Create an offscreen canvas to draw the video feed
    const offscreenCanvas = document.createElement('canvas');
    offscreenCanvas.width = srcEl.width;
    offscreenCanvas.height = srcEl.height;
    const offscreenCtx = offscreenCanvas.getContext('2d');

    // Draw the video feed onto the offscreen canvas
    const img = new Image();
    img.src = srcEl.src;
    img.onload = function () {
        offscreenCtx.drawImage(img, 0, 0, srcEl.width, srcEl.height);

        // Extract a 50x50 pixel area around the cursor
        const zoomSize = 50;
        const startX = Math.max(0, x - zoomSize / 2);
        const startY = Math.max(0, y - zoomSize / 2);

        // Clear the loupe canvas
        loupeCtx.clearRect(0, 0, loupe.width, loupe.height);

        // Draw the zoomed area onto the loupe canvas
        loupeCtx.drawImage(
            offscreenCanvas,
            startX, startY, zoomSize, zoomSize, // Source area
            0, 0, loupe.width, loupe.height    // Destination area
        );
    };
});

mainCanvas.addEventListener('mouseleave', function () {
    loupe.style.display = 'none'; // Hide the loupe when the mouse leaves the video feed
});