class TelescopeSim {
    constructor(canvas, longitude = 14.5058, latitude = 46.0569) {
        this.canvas = canvas;
        this.latitude = latitude * Math.PI / 180; // Convert to radians
		this.longitude = longitude; // Keep in degrees
        this.westPier = false;
		
        this.raAngle = 0;
        this.decAngle = 0;

        // Scene setup
        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(30, canvas.clientWidth / canvas.clientHeight, 0.1, 1000);
        this.camera.position.set(5, 5, 10);
        this.camera.lookAt(0, 0, 0);

        this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas });
        this.renderer.setSize(canvas.clientWidth, canvas.clientHeight);

        // OrbitControls
        this.controls = new THREE.OrbitControls(this.camera, this.canvas);
        this.controls.enableDamping = true;
        this.controls.dampingFactor = 0.05;
        this.controls.minDistance = 5;
        this.controls.maxDistance = 50;
        this.controls.enablePan = true;

        // Lighting
        this.ambientLight = new THREE.AmbientLight(0x404040, 0.6);
        this.scene.add(this.ambientLight);
        this.directionalLight = new THREE.DirectionalLight(0xffffff, 1.2);
        this.directionalLight.position.set(5, 5, 5);
        this.scene.add(this.directionalLight);

        this.directionalLight2 = new THREE.DirectionalLight(0xffffff, 1.2);
        this.directionalLight2.position.set(0, 10, 0);
        this.scene.add(this.directionalLight2);


        // Starfield
        const starGeometry = new THREE.BufferGeometry();
        const starCount = 5000;
        const starPositions = new Float32Array(starCount * 3);
        for (let i = 0; i < starCount * 3; i += 3) {
            const theta = Math.random() * 2 * Math.PI;
            const phi = Math.acos(2 * Math.random() - 1);
            const r = 100; // Large sphere radius
            starPositions[i] = r * Math.sin(phi) * Math.cos(theta);
            starPositions[i + 1] = r * Math.sin(phi) * Math.sin(theta);
            starPositions[i + 2] = r * Math.cos(phi);
        }
        starGeometry.setAttribute('position', new THREE.BufferAttribute(starPositions, 3));
        const starMaterial = new THREE.PointsMaterial({
            color: 0xffffff,
            size: 0.1,
            sizeAttenuation: true
        });
        const starfield = new THREE.Points(starGeometry, starMaterial);
        this.scene.add(starfield);

        // Materials
        this.bodyMaterial = new THREE.MeshPhongMaterial({ color: 0x2222aa, shininess: 50 });
        this.axisMaterial = new THREE.MeshPhongMaterial({ color: 0xff0000, shininess: 50 });
        this.shaftMaterial = new THREE.MeshPhongMaterial({ color: 0x555555, shininess: 50 });
        this.weightMaterial = new THREE.MeshPhongMaterial({ color: 0x333333, shininess: 50 });
        const textureLoader = new THREE.TextureLoader();
        const telescopeTexture = textureLoader.load('./static/PIPITREK.PNG');
        this.telescopeMaterial = new THREE.MeshPhongMaterial({
            map: telescopeTexture,
            shininess: 50,
            side: THREE.DoubleSide
        });
        this.telescopeBackMaterial = new THREE.MeshPhongMaterial({ color: 0x090909, shininess: 20 });

        // Groups
        this.polarGroup = new THREE.Group();
        this.raGroup = new THREE.Group();
        this.decGroup = new THREE.Group();
        this.scene.add(this.polarGroup);
        this.polarGroup.add(this.raGroup);
        this.raGroup.position.y = 0.6;
        this.raGroup.add(this.decGroup);

        // Tilt polarGroup
        this.polarGroup.rotation.z = -(Math.PI / 2 - this.latitude);

        // Vertical shaft
        const vshaftGeometry = new THREE.CylinderGeometry(0.2, 0.2, 4, 32);
        const vshaft = new THREE.Mesh(vshaftGeometry, this.bodyMaterial);
        vshaft.position.y = -2;
        vshaft.position.x = 0.12;
        this.scene.add(vshaft);

        // Polar axis - lower telescope body
        const raBodyGeometry = new THREE.CylinderGeometry(0.2, 0.2, 1, 32);
        const raBody = new THREE.Mesh(raBodyGeometry, this.bodyMaterial);
        const polarAxisGeometry = new THREE.CylinderGeometry(0.02, 0.02, 3, 32);
        const polarAxis = new THREE.Mesh(polarAxisGeometry, this.axisMaterial);
        this.polarGroup.add(raBody);
        this.polarGroup.add(polarAxis);

        // Dec axis
        const decAxisGeometry = new THREE.CylinderGeometry(0.02, 0.02, 2, 32);
        const decAxis = new THREE.Mesh(decAxisGeometry, this.axisMaterial);
        decAxis.rotation.x = Math.PI / 2;
        const decBodyGeometry = new THREE.CylinderGeometry(0.2, 0.2, 1, 32);
        const decBody = new THREE.Mesh(decBodyGeometry, this.bodyMaterial);
        decBody.rotation.x = Math.PI / 2;
        this.raGroup.add(decBody);
        this.raGroup.add(decAxis);

        // Counterweight shaft and weight
        const shaftGeometry = new THREE.CylinderGeometry(0.05, 0.05, 2.5, 32);
        const shaft = new THREE.Mesh(shaftGeometry, this.shaftMaterial);
        shaft.rotation.x = Math.PI / 2;
        shaft.position.z = 0.5;
        const weightGeometry = new THREE.CylinderGeometry(0.5, 0.5, 0.2, 32);
        const weight = new THREE.Mesh(weightGeometry, this.weightMaterial);
        weight.rotation.x = Math.PI / 2;
        weight.position.z = 1;
        const telescopeGeometry = new THREE.CylinderGeometry(0.5, 0.5, 2, 32, 1, true);
        const telescope = new THREE.Mesh(telescopeGeometry, this.telescopeMaterial);
        telescope.rotation.z = Math.PI *3 / 2;
        telescope.position.z = -1;
        const telescopeBackGeometry = new THREE.CylinderGeometry(0.51, 0.51, 0.2, 32);
        const telescopeBack = new THREE.Mesh(telescopeBackGeometry, this.telescopeBackMaterial);
        telescopeBack.rotation.z = Math.PI / 2;
        telescopeBack.position.z = -1;
        telescopeBack.position.x = -1;
        this.decGroup.add(telescope);
        this.decGroup.add(telescopeBack);
        this.decGroup.add(shaft);
        this.decGroup.add(weight);

        // Initial angles
        this.setAngles(this.raAngle, this.decAngle);

        // Start animation
        this.animate();
    }

    setAngles(ra, dec) {
        //dec = dec + latitude/Math.PI * 180;
		if(this.westPier) {
            ra = (ra + 180) % 360;
            dec = 180 - dec;
        } else {

        }
        while (dec > 180) dec -= 360;
        while (dec < -180) dec += 360;
        this.raAngle = ra;
        this.decAngle = dec;
        this.raGroup.rotation.y = (ra + 0) * Math.PI / 180;
        this.decGroup.rotation.z = dec * Math.PI / 180;
    }

    meridianFlip() {
        this.raAngle = (this.raAngle + 180) % 360;
        const decRot = Math.sign(this.decAngle) * (180 - 2 * Math.abs(this.decAngle));
        this.decAngle += decRot;
        this.westPier = !this.westPier;
        this.setAngles(this.raAngle, this.decAngle);
    }
    setPier(west = false) {
        this.westPier = west;
        this.setAngles(this.raAngle, this.decAngle);
    }

    parseRA(raStr) {
        const [hours, minutes, seconds] = raStr.split(':').map(Number);
        return hours + minutes / 60 + seconds / 3600;
    }

    parseDec(decStr) {
        const match = decStr.match(/([+-]?\d+)\*(\d+):(\d+)/);
        if (!match) return 0;
        const degrees = parseInt(match[1]);
        const minutes = parseInt(match[2]);
        const seconds = parseInt(match[3]);
        const sign = degrees >= 0 ? 1 : -1;
        return degrees + sign * (minutes / 60 + seconds / 3600);
    }

    getJulianDate() {
        const now = new Date();
        const year = now.getUTCFullYear();
        const month = now.getUTCMonth() + 1;
        const day = now.getUTCDate();
        const hours = now.getUTCHours() + now.getUTCMinutes() / 60 + now.getUTCSeconds() / 3600;
        let y = year, m = month;
        if (m <= 2) {
            y -= 1;
            m += 12;
        }
        const A = Math.floor(y / 100);
        const B = 2 - A + Math.floor(A / 4);
        const JD0 = Math.floor(365.25 * (y + 4716)) + Math.floor(30.6001 * (m + 1)) + day + B - 1524.5;
        return JD0 + hours / 24;
    }

    calculateLST(longitude) {
        const JD = this.getJulianDate();
        const D = JD - 2451545.0;
        let GMST = 6.697374558 + 0.06570982441908 * D + 1.00273790935 * (JD % 1) * 24;
        GMST = GMST % 24;
        if (GMST < 0) GMST += 24;
        const LST = GMST + longitude / 15;
        return LST % 24;
    }

    pointTelescope(raStr, decStr) {
        const raHours = this.parseRA(raStr);
        const decDegrees = this.parseDec(decStr);
        const lstHours = this.calculateLST(this.longitude);
        let raDiff = (raHours - lstHours) * 15;
        raDiff = ((raDiff % 360) + 360) % 360;
        this.setAngles(raDiff, decDegrees);
    }

    resize(width, height) {
        this.camera.aspect = width / height;
        this.camera.updateProjectionMatrix();
        this.renderer.setSize(width, height);
    }

    animate() {
        requestAnimationFrame(() => this.animate());
        this.controls.update();
        this.renderer.render(this.scene, this.camera);
    }
}