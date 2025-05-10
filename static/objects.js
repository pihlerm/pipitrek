import * as THREE from 'three';
import * as TextUtils from './textutils.js';

// Function to create a 2x2m observing platform with a 20cm high fence
export function createObservingPlatform() {
    const platformGroup = new THREE.Group();
    platformGroup.name = 'ObservingPlatform';

    // Metallic material
    const material = new THREE.MeshStandardMaterial({
        color: 0x808080, // Gray
        metalness: 0.8,  // High metalness for shiny look
        roughness: 0.2,  // Low roughness for polished surface
        side: THREE.DoubleSide, // Ensure visible from below in VR
    });

    // Platform base: 2m x 0.05m x 2m
    const baseGeometry = new THREE.BoxGeometry(2, 0.05, 2);
    const baseMesh = new THREE.Mesh(baseGeometry, material);
    baseMesh.position.set(0, -0.025, 0); // Center at y=0 (relative to platformGroup)
    baseMesh.name = 'PlatformBase';
    platformGroup.add(baseMesh);

    // Fence: Four railings, each 2m long, 0.2m high, 0.05m thick
    const fenceGeometry = new THREE.BoxGeometry(2, 0.2, 0.05);
    
    // Front fence (z = -1m)
    const frontFence = new THREE.Mesh(fenceGeometry, material);
    frontFence.position.set(0, 0.1, -1); // 0.2m/2 = 0.1m height, at z=-1m
    frontFence.name = 'FrontFence';
    platformGroup.add(frontFence);

    // Back fence (z = +1m)
    const backFence = new THREE.Mesh(fenceGeometry, material);
    backFence.position.set(0, 0.1, 1);
    backFence.name = 'BackFence';
    platformGroup.add(backFence);

    // Left fence (x = -1m, rotate 90°)
    const leftFence = new THREE.Mesh(fenceGeometry, material);
    leftFence.position.set(-1, 0.1, 0);
    leftFence.rotation.y = Math.PI / 2; // Rotate to align along z-axis
    leftFence.name = 'LeftFence';
    platformGroup.add(leftFence);

    // Right fence (x = +1m, rotate 90°)
    const rightFence = new THREE.Mesh(fenceGeometry, material);
    rightFence.position.set(1, 0.1, 0);
    rightFence.rotation.y = Math.PI / 2;
    rightFence.name = 'RightFence';
    platformGroup.add(rightFence);

    // Position platform at foot level (assuming eye height ~1.6m in VR)
    platformGroup.position.set(0, -1.6, 0);

    // Prevent raycasting interference (e.g., with DigitalBacon-UI)
    platformGroup.traverse((child) => {
        if (child.isMesh) child.raycast = null;
    });

    return platformGroup;
}

export function addCoordinateAxes(group) {
    // Materials for axes
    const xMaterial = new THREE.LineBasicMaterial({ color: 0xff0000 }); // Red for x
    const yMaterial = new THREE.LineBasicMaterial({ color: 0x00ff00 }); // Green for y
    const zMaterial = new THREE.LineBasicMaterial({ color: 0x0000ff }); // Blue for z

    // Geometries for axes (lines of length 5)
    const xGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(5, 0, 0)
    ]);
    const yGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0, 5, 0)
    ]);
    const zGeometry = new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(0, 0, 0),
        new THREE.Vector3(0, 0, 5)
    ]);

    // Create lines
    const xAxis = new THREE.Line(xGeometry, xMaterial);
    const yAxis = new THREE.Line(yGeometry, yMaterial);
    const zAxis = new THREE.Line(zGeometry, zMaterial);

    // Add axes to scene
    group.add(xAxis);
    group.add(yAxis);
    group.add(zAxis);

    // Add text labels at the end of each axis
    const xLabel = TextUtils.createTextSprite('X');
    xLabel.scale.set(1, 1, 1);
    xLabel.position.set(5.5, 0, 0); // Slightly beyond x-axis end
    const yLabel = TextUtils.createTextSprite('Y');
    yLabel.scale.set(1, 1, 1);
    yLabel.position.set(0, 5.5, 0); // Slightly beyond y-axis end
    const zLabel = TextUtils.createTextSprite('Z');
    zLabel.scale.set(1, 1, 1);
    zLabel.position.set(0, 0, 5.5); // Slightly beyond z-axis end

    // Add labels to scene
    group.add(xLabel);
    group.add(yLabel);
    group.add(zLabel);
}    

export function addSkyPoles(scene) {
    // Materials for axes
    const mat = new THREE.LineBasicMaterial({ color: 0x00ff00 }); // Green for y

    // Add text labels at the end of each axis
    const nLabel = TextUtils.createTextSprite('N');
    nLabel.scale.set(2, 2, 2);
    nLabel.position.set(100, 0, 0);
    
    const sLabel = TextUtils.createTextSprite('S');
    sLabel.scale.set(2, 2, 2);
    sLabel.position.set(-100, 0, 0); 

    const eLabel = TextUtils.createTextSprite('E');
    eLabel.scale.set(2, 2, 2);
    eLabel.position.set(0, 0, 100);

    const wLabel = TextUtils.createTextSprite('W');
    wLabel.scale.set(2, 2, 2);
    wLabel.position.set(0, 0, -100);
    // Add labels to scene
    scene.add(nLabel);
    scene.add(sLabel);
    scene.add(eLabel);
    scene.add(wLabel);
}    

export function  addGround2(height, scene) {
    const loader = new THREE.TextureLoader();
    loader.load('./img/Ground042_1K-JPG_Color.jpg', (texture) => {
        texture.wrapS = texture.wrapT = THREE.RepeatWrapping;
        texture.repeat.set(30, 30); // Tile the texture for more detail
        texture.encoding = THREE.sRGBEncoding;
        texture.colorSpace = THREE.SRGBColorSpace;
    
        const groundGeometry = new THREE.CircleGeometry(100, 64);
        const groundMaterial = new THREE.MeshStandardMaterial({
            map: texture,
            side: THREE.DoubleSide,
        });

        const ground = new THREE.Mesh(groundGeometry, groundMaterial);
        ground.position.set(0, -height, 0);
        ground.rotation.x = -Math.PI / 2;

        //ground.receiveShadow = true; // Optional: if you use lighting/shadows
        scene.add(ground);
    });
}

export function addGround(height) {

    const loader = new THREE.TextureLoader();
    const loadTexture = (url) => loader.load(url);
    const colorMap = loadTexture('./img/Ground038_1K-JPG_Color.jpg');
    colorMap.encoding = THREE.sRGBEncoding;
    colorMap.colorSpace = THREE.SRGBColorSpace;

    const groundGeometry = new THREE.CircleGeometry(100, 64);
    const groundMaterial = new THREE.MeshStandardMaterial({
        map: colorMap,
        normalMap: loadTexture('./img/Ground038_1K-JPG_NormalGL.jpg'),
        roughnessMap: loadTexture('./img/Ground038_1K-JPG_Roughness.jpg'),
        //aoMap: loadTexture('/static/img/Ground042_1K-JPG_AmbientOcclusion.jpg'),
        //displacementMap: loadTexture('/static/img/Ground042_1K-JPG_Displacement.jpg'),
        //displacementScale: 1, // Adjust based on scene scale
        side: THREE.DoubleSide,
        transparent: true,
        opacity: 0.5
    });

    const repeat = 30;
    [
        'map',
        'normalMap',
        'roughnessMap',
        //'aoMap',
        //'displacementMap'
    ].forEach(key => {
        if (groundMaterial[key]) {
            groundMaterial[key].wrapS = groundMaterial[key].wrapT = THREE.MirroredRepeatWrapping;
            groundMaterial[key].repeat.set(repeat, repeat);
        }
    });

    const ground = new THREE.Mesh(groundGeometry, groundMaterial);
    ground.position.set(0, -height, 0);
    ground.rotation.x = -Math.PI / 2;

    //ground.receiveShadow = true; // Optional: if you use lighting/shadows
    return ground;

}

export function addTrees(scene) {
    const loader2 = new  GLTFLoader();
    loader2.load('./img/searsia_burchellii_4k.gltf/searsia_burchellii_4k.gltf', (gltf) => {
        const originalTree = gltf.scene;
    
        const treePositions = [
            [10, 0, 15],
            [-12, 0, -8],
            [5, 0, -20],
            [20, 0, 10]
        ];
    
        for (const [x, y, z] of treePositions) {
            const treeClone = originalTree.clone(true); // deep clone
            treeClone.position.set(x, y, z);
            scene.add(treeClone);
        }
    });
/*        loader2.load('/static/img/searsia_burchellii_4k.gltf/searsia_burchellii_4k.gltf', (gltf) => {
        const model = gltf.scene;
    
        // Find the mesh to instance (assuming it's a single mesh tree)
        let treeMesh;
        model.traverse((child) => {
            if (child.isMesh && !treeMesh) {
                treeMesh = child;
            }
        });
    
        if (!treeMesh) {
            console.error("No mesh found in tree model");
            return;
        }
    
        const geometry = treeMesh.geometry;
        const material = treeMesh.material;
    
        // Number of instances
        const count = 50;
        const instancedMesh = new THREE.InstancedMesh(geometry, material, count);
    
        // Optional: allow interaction
        instancedMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    
        // Add instances at various positions
        const dummy = new THREE.Object3D();
        for (let i = 0; i < count; i++) {
            
            const phi = Math.random()*2*Math.PI;
            const r = Math.random()*25+25;

            let x = r*Math.sin(phi);
            let z = r*Math.cos(phi);
            const scale = 0.8 + Math.random() * 0.4;
    
            dummy.position.set(x, 0, z);
            dummy.scale.set(scale, scale, scale);
            dummy.updateMatrix();
    
            instancedMesh.setMatrixAt(i, dummy.matrix);
        }
    
        scene.add(instancedMesh);
    });*/



}