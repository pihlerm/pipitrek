
const mainCanvas = document.getElementById('canvas');
const loupe = document.getElementById('loupe');
const loupeCtx = loupe.getContext('2d');
var loupeScale = 3; // Magnification factor
var loupeX = 0;
var loupeY = 0;


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
}

mainCanvas.addEventListener('mousemove', function (event) {
    
    // Position the loupe near the cursor
    loupe.style.left = `${event.clientX + 10}px`;
    loupe.style.top = `${event.clientY + 10}px`;
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