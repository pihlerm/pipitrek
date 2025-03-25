function make_wheel() {
    const canvas = document.getElementById('pec-wheel');
    const ctx = canvas.getContext('2d');
    const rotationAngleInput = document.getElementById('pec-position');

    let rotationAngle = 0; // Current rotation angle in degrees
    let isDragging = false;
    let isInputMode = false; // Track whether the wheel is in input mode
    let startAngle = 0;
    let startX = 0; // Initial mouse X position
    let startY = 0; // Initial mouse Y position
    let offsetAngle = 120;
    let direction = -1;
    const dragThreshold = 10; // Minimum distance to start dragging

    // Draw the wheel
    function drawWheel() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        const centerX = canvas.width / 2;
        const centerY = canvas.height / 2;
        const radius = canvas.width / 2 - 10;

        // Draw the outer circle
        ctx.beginPath();
        ctx.arc(centerX, centerY, radius, 0, 2 * Math.PI);
        ctx.fillStyle = isInputMode ? 'lightgreen' : '#909090'; // Change color in input mode
        ctx.fill();
        ctx.strokeStyle = '#000';
        ctx.lineWidth = 2;
        ctx.stroke();

        // Draw the mark
        const markLength = 20;

        const markX = centerX + radius * 0.8 * Math.cos((offsetAngle + rotationAngle - 90) * (Math.PI / 180));
        const markY = centerY + radius * 0.8 * Math.sin((offsetAngle + rotationAngle - 90) * (Math.PI / 180));

        ctx.beginPath();
        ctx.moveTo(centerX, centerY);
        ctx.lineTo(markX, markY);
        ctx.strokeStyle = 'red';
        ctx.lineWidth = 3;
        ctx.stroke();

        // Draw the zero mark
        const zeromarkX1 = centerX + 1.1 * radius * Math.cos((offsetAngle - 90) * (Math.PI / 180));
        const zeromarkY1 = centerY + 1.1 * radius * Math.sin((offsetAngle - 90) * (Math.PI / 180));
        const zeromarkX2 = centerX + 1.3 * radius * Math.cos((offsetAngle - 90) * (Math.PI / 180));
        const zeromarkY2 = centerY + 1.3 * radius * Math.sin((offsetAngle - 90) * (Math.PI / 180));

        ctx.beginPath();
        ctx.moveTo(zeromarkX1, zeromarkY1);
        ctx.lineTo(zeromarkX2, zeromarkY2);
        ctx.strokeStyle = 'black';
        ctx.lineWidth = 3;
        ctx.stroke();
    }

    // Convert mouse position to angle
    function getMouseAngle(event) {
        const rect = canvas.getBoundingClientRect();
        const centerX = rect.left + canvas.width / 2;
        const centerY = rect.top + canvas.height / 2;

        const dx = event.clientX - centerX;
        const dy = event.clientY - centerY;

        const angle = Math.atan2(dy, dx) * (180 / Math.PI);
        return angle >= 0 ? angle : 360 + angle;
    }

    // Calculate distance between two points
    function getDistance(x1, y1, x2, y2) {
        if(x1==0 && y1==0) return 0;
        return Math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2);
    }

    // Mouse down event
    canvas.addEventListener('mousedown', (event) => {
        startX = event.clientX; // Store the initial mouse X position
        startY = event.clientY; // Store the initial mouse Y position
        startAngle = getMouseAngle(event) - rotationAngle;
    });

    // Mouse move event
    canvas.addEventListener('mousemove', (event) => {
        const distance = getDistance(startX, startY, event.clientX, event.clientY);
        if(isInputMode ){
            if (!isDragging && distance > dragThreshold) {
                isDragging = true; // Start dragging only if the distance exceeds the threshold
            }
    
            if (isDragging) {
                const currentAngle = getMouseAngle(event);
                rotationAngle = (currentAngle - startAngle + 360) % 360;
                setPECText(rotationAngle);
                drawWheel();
            }    
        }
    });

    // Mouse up event
    canvas.addEventListener('mouseup', () => {
        if(!isDragging) {
            isInputMode = !isInputMode; // Toggle input mode
            drawWheel(); // Redraw the wheel with the updated color    
        }
        startX = 0;
        startY = 0;
        isDragging = false;
    });

    // Mouse leave event
    canvas.addEventListener('mouseleave', () => {
        startX = 0;
        startY = 0;
        isDragging = false;
    });
    
    rotationAngleInput.addEventListener('input', (event) => {
        const percent = parseFloat(event.target.value); // Get the input value as a number
        if (!isNaN(percent) && percent >= 0 && percent <= 100) {
            // Update the rotation angle based on the input percent
            old = isInputMode;
            isInputMode = false;
            setPECPositon(percent);
            isInputMode = old;
            drawWheel(); // Redraw the wheel
        } else {
            // Reset the input if the value is invalid
            event.target.value = rotationAngleInput.value; // Keep the previous valid value
        }
    });
    

    function setPECText(angle) {
        let percent = (((360 + direction * angle) % 360) / 360) * 100;
        percent = percent % 100;
        rotationAngleInput.value = percent.toFixed(0);
    }

    // Set rotation angle programmatically
    function setPECPositon(pos) {
        if(isInputMode) return;
        rotationAngle = (360 + direction * (pos * 360 / 100)) % 360;
        setPECText(rotationAngle);
        drawWheel();
    }

    // Get rotation angle programmatically
    function getPECPosition() {
        let percent = (((360 + direction * rotationAngle) % 360) / 360) * 100;
        percent = percent % 100;
        return percent;
    }

    // Initial draw
    drawWheel();
    return {
        setPECPositon: setPECPositon,
        getPECPosition: getPECPosition
    };
}