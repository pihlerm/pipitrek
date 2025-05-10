import * as THREE from 'three';

export function createTextSprite(text) {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');

    // Text settings
    context.font = 'Bold 28px Arial';
    context.fillStyle = 'white';
    context.textAlign = 'center';
    context.textBaseline = 'middle';

    // Split text into lines
    const lines = text.split('\n');
    const lineHeight = 32; // Spacing for 28px font
    const padding = 2; // Padding around text (pixels)

    // Calculate dimensions
    let maxWidth = 0;
    lines.forEach(line => {
        const metrics = context.measureText(line);
        maxWidth = Math.max(maxWidth, metrics.width);
    });
    const totalHeight = lines.length * lineHeight;
    
    // Set canvas size with padding
    canvas.width = Math.ceil(maxWidth) + padding * 2;
    canvas.height = totalHeight + padding * 2;

    // Clear background (fully transparent)
    context.fillStyle = 'rgba(0, 0, 0, 0)';
    context.fillRect(0, 0, canvas.width, canvas.height);

    // Re-apply text settings (after canvas resize)
    context.font = 'Bold 28px Arial';
    context.fillStyle = 'white';
    context.textAlign = 'center';
    context.textBaseline = 'middle';

    // Render each line, centered
    const startY = (canvas.height - totalHeight) / 2 + lineHeight / 2;
    lines.forEach((line, index) => {
        const y = startY + index * lineHeight;
        context.fillText(line, canvas.width / 2, y);
    });

    // Create sprite with transparent material
    const texture = new THREE.CanvasTexture(canvas);
    const spriteMaterial = new THREE.SpriteMaterial({
        map: texture,
        alphaTest: 0.1,     // <— discard fully‑transparent pixels
        transparent: true
    });
    const sprite = new THREE.Sprite(spriteMaterial);
    // Set sprite scale to match canvas dimensions
    sprite.scale.set(canvas.width, canvas.height, 1);
    sprite.userData.width = canvas.width;
    sprite.userData.height = canvas.height;
    return sprite;
}

export function  createTextSprite2(text) {
    
    if(typeof this.font == 'undefined') return null;

    const group = new THREE.Group();
    
    // Materials from example
    const color = 0x006699;
    const matDark = new THREE.LineBasicMaterial({
        color: color,
        side: THREE.DoubleSide
    });
    const matLite = new THREE.MeshBasicMaterial({
        color: color,
        transparent: true,
        opacity: 0.4,
        side: THREE.DoubleSide
    });

    // Generate shapes with font (handles newlines)
    const fontSize = 100;
    const shapes = this.font.generateShapes(text, fontSize);
    const geometry = new THREE.ShapeGeometry(shapes);

    // Center text block
    geometry.computeBoundingBox();
    const xMid = -0.5 * (geometry.boundingBox.max.x - geometry.boundingBox.min.x);
    const yMid = -0.5 * (geometry.boundingBox.max.y - geometry.boundingBox.min.y);
    geometry.translate(xMid, yMid, 0);

    // Create mesh for face
    const textMesh = new THREE.Mesh(geometry, matLite);

    // Create wireframe for edges
    const edges = new THREE.EdgesGeometry(geometry);
    const textEdges = new THREE.LineSegments(edges, matDark);

    // Add to group
    group.add(textMesh, textEdges);

    return group;
}