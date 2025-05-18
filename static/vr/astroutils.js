import * as THREE from 'three';

/**
* Convert a string representation of Right Ascension (RA) to decimal hours. 
* @param {string} raStr - The RA string in the format "hh:mm:ss".
* @return {number} - The decimal hours representation of RA.
* @throws {Error} - Throws an error if the input string is not in the correct format.
*/
export function parseRA(raStr) {
    const [hours, minutes, seconds] = raStr.split(':').map(Number);
    return hours + minutes / 60 + seconds / 3600;
}

/**
* Convert a string representation of Declination (Dec) to decimal degrees.
* @param {string} decStr - The Dec string in the format "±dd:mm:ss".
* @return {number} - The decimal degrees representation of Dec.
* @throws {Error} - Throws an error if the input string is not in the correct format.
*/
export function parseDec(decStr) {
    // Allow seconds to be fractional (e.g., 12*34:56.78)
    const match = decStr.match(/([+-]?\d+)\*(\d+):(\d+(?:\.\d+)?)/);
    if (!match) return 0;
    const degrees = parseInt(match[1]);
    const minutes = parseInt(match[2]);
    const seconds = parseFloat(match[3]);
    const sign = degrees >= 0 ? 1 : -1;
    return degrees + sign * (minutes / 60 + seconds / 3600);
}

/** 
 * Calculate the Julian Date for a given date.
 * @param {Date} now - The date for which to calculate the Julian Date.
 * @return {number} - The Julian Date.
 * @throws {Error} - Throws an error if the input date is invalid.
 * @description The Julian Date is a continuous count of days since the beginning of the Julian Period on January 1, 4713 BC.
 * The Julian Date is used in astronomy and is useful for calculating time intervals between events.
 */
export function getJulianDate(now) {
    const year = now.getUTCFullYear();
    const month = now.getUTCMonth() + 1;
    const day = now.getUTCDate();
    const hours = now.getUTCHours() + now.getUTCMinutes() / 60 + (now.getUTCSeconds()+now.getUTCMilliseconds()/1000) / 3600;
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


function frac(X) {
    X = X - Math.floor(X);
    if (X<0) X = X + 1.0;
    return X;		
}

/**
 * Convert a decimal degree value to a string representation in the format "dd*mm:ss".
 * @param {number} degrees - The decimal degree value to convert.
 * @return {string} - The string representation of the decimal degree value.
 */

export function Degrees(degrees) {
    const sign = degrees < 0 ? -1 : 1;
    const absDeg = Math.abs(degrees);

    const deg = Math.floor(absDeg);
    const minFloat = 60.0 * (absDeg - deg);
    const min = Math.floor(minFloat);
    const sec = Math.round(60.0 * (minFloat - min)*10.0)/10.0;

    const pad = (v) => (v < 10 ? '0' + v : v);
    
    const signedDeg = (sign == 1 ? '+' : '-') +  pad(deg);

    return `${signedDeg}*${pad(min)}:${pad(sec)}`;
}

/**
 * Convert a decimal time value to a string representation in the format "hh:mm:ss".
 * @param {number} time - The decimal time value to convert.
 * @return {string} - The string representation of the decimal time value.
 */
export function HoursMinutesSeconds(time) {
    var h = Math.floor(time);
    var min = Math.floor(60.0*frac(time));
    var secs = Math.round(60.0*(60.0*frac(time)-min)*10.0)/10.0;
    var str;
    if (min>=10) str=h+":"+min;
    else  str=h+":0"+min;
    if (secs<10) str = str + ":0"+secs;
    else str = str + ":"+secs;
    return " " + str;       
 }
   
/**
 * Calculate the Local Sidereal Time (LST) based on the given longitude in degrees.
 * @param {number} longitudeDegrees - The longitude in degrees.
 * @return {number} - The Local Sidereal Time in hours.
 * @throws {Error} - Throws an error if the input longitude is invalid.
 */

 export function calculateLST(longitudeDegrees) {
    const now = new Date(); // browser time (assumed UTC or converted below)
    const JD = getJulianDate(now);
    const T = (JD - 2451545.0) / 36525.0;

    // Calculate Greenwich Mean Sidereal Time (GMST) in seconds
    let GMST = 280.46061837 +
               360.98564736629 * (JD - 2451545) +
               0.000387933 * T * T -
               (T * T * T) / 38710000;

    // Normalize to 0–360
    GMST = ((GMST % 360) + 360) % 360;

    // Local Sidereal Time
    let LST = GMST + longitudeDegrees;

    // Normalize to 0–360
    LST = ((LST % 360) + 360) % 360;

    // Convert to hours
    return LST / 15;
}

/**
 * Convert a string representation of Right Ascension (RA) and Declination (Dec) to a 3D position vector on a sphere.
 * @param {string} raStr - The RA string in the format "hh:mm:ss".
 * @param {string} decStr - The Dec string in the format "±dd*mm:ss".
 * @param {THREE.Group} group - The THREE.Group object relative to which raStr/decStr are given. null for local space. If given, the position will be transformed from group to world coordinates.
 * @param {number} r - The radius of the sphere (default is 100).
 * @return {number[]} - The 3D position vector [x, y, z].
 * @throws {Error} - Throws an error if the input strings are not in the correct format.
 */
export function positionFromRADEC(raStr, decStr, group = null, r=100) {
    const ra = parseRA(raStr)/12 * Math.PI; // Hours to radians
    const dec = parseDec(decStr)/180 * Math.PI; // Degrees to radians
    return positionFromRADECrad(ra, dec, group, r);
}

export function positionFromRADECrad(ra, dec, group = null, r=100) {
    // Set position
    var pos = [];
    pos[0] = -r * Math.cos(ra)*Math.cos(dec); // -x
    pos[1] = r * Math.sin(dec); // y
    pos[2] = r * Math.sin(ra) * Math.cos(dec); // z
    if(group) {
        const v = new THREE.Vector3(pos[0], pos[1], pos[2]);
        group.updateMatrixWorld(true);
        v.applyMatrix4(group.matrixWorld);
        pos[0] = v.x;
        pos[1] = v.y;
        pos[2] = v.z;
    }
    return pos;
}

export function getRaDecFromPosition(vec, group, r = 100, world = false) {
    const v = vec.clone();

    if (world) {
        group.updateMatrixWorld(true);
        const inv = new THREE.Matrix4().copy(group.matrixWorld).invert();
        v.applyMatrix4(inv); // Transform from world space to group local space
    }

    // Normalize to radius
    v.normalize();

    // Inverse of your original mapping:
    let dec = Math.asin(v.y); // y = sin(dec)
    let ra = Math.atan2(v.z, -v.x); // z = sin(ra) * cos(dec), -x = cos(ra) * cos(dec)

    // Ensure RA is in [0, 2π]
    ra =(ra + 2 * Math.PI) % (2 * Math.PI);
    // Convert to hours
    ra = ra / Math.PI * 12; // Radians to hours
    dec = dec / Math.PI * 180; // Radians to degrees
    return [
        HoursMinutesSeconds(ra),
        Degrees(dec)
    ];
}


/*
    * Compute the center of a set of points in 3D space.
    * @param {THREE.Vector3[]} P - Array of THREE.Vector3 points.
    * @returns {THREE.Vector3} - The center point.
    */

export function getCenter(P) {
    const center = new THREE.Vector3();
    for (let v of P) center.add(v);
    center.divideScalar(P.length);
    return center;
}
/**
 * Replace this.sphereIntersects with its convex hull (spherical).
 * Uses tangent‑plane projection + 2D convex hull.
 */
export function makeSphericalPolygonConvex(P) {
    
    const n = P.length;
    if (n < 3) return null;                // fewer than 3 points is already “convex”

    // 1) find average direction
    const center = getCenter(P).normalize(); // center of polygon

    // 2) build orthonormal basis (u,v) tangent at center
    //    choose any vector not colinear with center
    const arbitrary = Math.abs(center.x) < 0.9 ? new THREE.Vector3(1,0,0) : new THREE.Vector3(0,1,0);

    const u = new THREE.Vector3().crossVectors(arbitrary, center).normalize();
    const v = new THREE.Vector3().crossVectors(center, u).normalize();

    // 3) project each Vi onto (u,v) plane → 2D coords
    const pts2D = P.map(V => {
        return {
            x: V.dot(u),
            y: V.dot(v),
            orig: V
        };
    });

    // 4) compute 2D convex hull by Andrew’s monotone chain
    pts2D.sort((a,b)=> a.x===b.x ? a.y-b.y : a.x-b.x);
    const cross = (o,a,b) => (a.x-o.x)*(b.y-o.y) - (a.y-o.y)*(b.x-o.x);

    const lower = [];
    for (let p of pts2D) {
        while (lower.length >= 2 && cross(lower[lower.length-2], lower[lower.length-1], p) <= 0) {
            lower.pop();
        }
        lower.push(p);
    }
    const upper = [];
    for (let i=pts2D.length-1; i>=0; i--) {
        const p = pts2D[i];
        while (upper.length >= 2 && cross(upper[upper.length-2], upper[upper.length-1], p) <= 0) {
            upper.pop();
        }
        upper.push(p);
    }
    upper.shift(); lower.pop();
    const hull2D = lower.concat(upper);

    // 5) rebuild sphereIntersects in hull order
    return hull2D.map(p=> p.orig );
}

export function isPointInConvexSphericalPolygon( P /*THREE.Vector3 unit*/, polyVerts ) {
    const m = polyVerts.length;
    for ( let i = 0; i < m; ++i ) {
        // grab edge endpoints
        const A = polyVerts[i];
        const B = polyVerts[(i+1)%m];
        // great‑circle normal:
        const N = new THREE.Vector3().crossVectors( A, B ).normalize();
        // if P is “behind” this edge, reject
        if ( N.dot(P) < 0 ) return false;
    }
    return true;
}


export function base64ToBlob(base64, mime = 'image/jpeg') {
    const binary = atob(base64);
    const len = binary.length;
    const buffer = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        buffer[i] = binary.charCodeAt(i);
    }
    return new Blob([buffer], { type: mime });
}

// https://celestialprogramming.com/articles/starColors/starColors.html
const BVtoRGB_colors_WRec709 = [
    {r: 1, g: 0.5092, b: 0.1876},    {r: 1, g: 0.5116, b: 0.1902},
    {r: 1, g: 0.5140, b: 0.1928},    {r: 1, g: 0.5164, b: 0.1954},
    {r: 1, g: 0.5188, b: 0.1981},    {r: 1, g: 0.5212, b: 0.2008},
    {r: 1, g: 0.5237, b: 0.2036},    {r: 1, g: 0.5261, b: 0.2064},
    {r: 1, g: 0.5286, b: 0.2092},    {r: 1, g: 0.5311, b: 0.2120},
    {r: 1, g: 0.5336, b: 0.2149},    {r: 1, g: 0.5361, b: 0.2178},
    {r: 1, g: 0.5386, b: 0.2208},    {r: 1, g: 0.5411, b: 0.2238},
    {r: 1, g: 0.5437, b: 0.2268},    {r: 1, g: 0.5462, b: 0.2299},
    {r: 1, g: 0.5488, b: 0.2330},    {r: 1, g: 0.5514, b: 0.2361},
    {r: 1, g: 0.5540, b: 0.2393},    {r: 1, g: 0.5566, b: 0.2425},
    {r: 1, g: 0.5593, b: 0.2458},    {r: 1, g: 0.5619, b: 0.2491},
    {r: 1, g: 0.5646, b: 0.2524},    {r: 1, g: 0.5672, b: 0.2558},
    {r: 1, g: 0.5699, b: 0.2593},    {r: 1, g: 0.5726, b: 0.2627},
    {r: 1, g: 0.5753, b: 0.2662},    {r: 1, g: 0.5781, b: 0.2698},
    {r: 1, g: 0.5808, b: 0.2734},    {r: 1, g: 0.5836, b: 0.2770},
    {r: 1, g: 0.5863, b: 0.2807},    {r: 1, g: 0.5891, b: 0.2845},
    {r: 1, g: 0.5919, b: 0.2883},    {r: 1, g: 0.5948, b: 0.2921},
    {r: 1, g: 0.5976, b: 0.2960},    {r: 1, g: 0.6004, b: 0.2999},
    {r: 1, g: 0.6033, b: 0.3039},    {r: 1, g: 0.6062, b: 0.3079},
    {r: 1, g: 0.6091, b: 0.3120},    {r: 1, g: 0.6120, b: 0.3161},
    {r: 1, g: 0.6149, b: 0.3203},    {r: 1, g: 0.6179, b: 0.3245},
    {r: 1, g: 0.6208, b: 0.3288},    {r: 1, g: 0.6238, b: 0.3331},
    {r: 1, g: 0.6268, b: 0.3375},    {r: 1, g: 0.6298, b: 0.3420},
    {r: 1, g: 0.6328, b: 0.3465},    {r: 1, g: 0.6359, b: 0.3511},
    {r: 1, g: 0.6389, b: 0.3557},    {r: 1, g: 0.6420, b: 0.3604},
    {r: 1, g: 0.6451, b: 0.3651},    {r: 1, g: 0.6482, b: 0.3699},
    {r: 1, g: 0.6514, b: 0.3748},    {r: 1, g: 0.6545, b: 0.3797},
    {r: 1, g: 0.6577, b: 0.3847},    {r: 1, g: 0.6608, b: 0.3897},
    {r: 1, g: 0.6640, b: 0.3948},    {r: 1, g: 0.6673, b: 0.4000},
    {r: 1, g: 0.6705, b: 0.4052},    {r: 1, g: 0.6737, b: 0.4106},
    {r: 1, g: 0.6770, b: 0.4159},    {r: 1, g: 0.6803, b: 0.4214},
    {r: 1, g: 0.6836, b: 0.4269},    {r: 1, g: 0.6869, b: 0.4325},
    {r: 1, g: 0.6903, b: 0.4381},    {r: 1, g: 0.6936, b: 0.4439},
    {r: 1, g: 0.6970, b: 0.4497},    {r: 1, g: 0.7004, b: 0.4555},
    {r: 1, g: 0.7038, b: 0.4615},    {r: 1, g: 0.7073, b: 0.4675},
    {r: 1, g: 0.7107, b: 0.4736},    {r: 1, g: 0.7142, b: 0.4798},
    {r: 1, g: 0.7177, b: 0.4861},    {r: 1, g: 0.7212, b: 0.4924},
    {r: 1, g: 0.7247, b: 0.4989},    {r: 1, g: 0.7283, b: 0.5054},
    {r: 1, g: 0.7318, b: 0.5120},    {r: 1, g: 0.7354, b: 0.5186},
    {r: 1, g: 0.7390, b: 0.5254},    {r: 1, g: 0.7427, b: 0.5323},
    {r: 1, g: 0.7463, b: 0.5392},    {r: 1, g: 0.7500, b: 0.5462},
    {r: 1, g: 0.7537, b: 0.5534},    {r: 1, g: 0.7574, b: 0.5606},
    {r: 1, g: 0.7611, b: 0.5679},    {r: 1, g: 0.7649, b: 0.5753},
    {r: 1, g: 0.7687, b: 0.5828},    {r: 1, g: 0.7724, b: 0.5904},
    {r: 1, g: 0.7763, b: 0.5981},    {r: 1, g: 0.7801, b: 0.6059},
    {r: 1, g: 0.7839, b: 0.6138},    {r: 1, g: 0.7878, b: 0.6218},
    {r: 1, g: 0.7917, b: 0.6299},    {r: 1, g: 0.7956, b: 0.6381},
    {r: 1, g: 0.7996, b: 0.6464},    {r: 1, g: 0.8035, b: 0.6549},
    {r: 1, g: 0.8075, b: 0.6634},    {r: 1, g: 0.8115, b: 0.6721},
    {r: 1, g: 0.8155, b: 0.6808},    {r: 1, g: 0.8196, b: 0.6897},
    {r: 1, g: 0.8237, b: 0.6987},    {r: 1, g: 0.8278, b: 0.7078},
    {r: 1, g: 0.8319, b: 0.7170},    {r: 1, g: 0.8360, b: 0.7264},
    {r: 1, g: 0.8402, b: 0.7359},    {r: 1, g: 0.8443, b: 0.7455},
    {r: 1, g: 0.8485, b: 0.7552},    {r: 1, g: 0.8528, b: 0.7650},
    {r: 1, g: 0.8570, b: 0.7750},    {r: 1, g: 0.8613, b: 0.7851},
    {r: 1, g: 0.8656, b: 0.7954},    {r: 1, g: 0.8699, b: 0.8058},
    {r: 1, g: 0.8742, b: 0.8163},    {r: 1, g: 0.8786, b: 0.8269},
    {r: 1, g: 0.8829, b: 0.8377},    {r: 1, g: 0.8873, b: 0.8487},
    {r: 1, g: 0.8918, b: 0.8597},    {r: 1, g: 0.8962, b: 0.8710},
    {r: 1, g: 0.9007, b: 0.8823},    {r: 1, g: 0.9052, b: 0.8939},
    {r: 1, g: 0.9097, b: 0.9055},    {r: 1, g: 0.9142, b: 0.9174},
    {r: 1, g: 0.9188, b: 0.9293},    {r: 1, g: 0.9234, b: 0.9415},
    {r: 1, g: 0.9280, b: 0.9538},    {r: 1, g: 0.9326, b: 0.9662},
    {r: 1, g: 0.9373, b: 0.9789},    {r: 1, g: 0.9419, b: 0.9917},
    {r: 0.9954, g: 0.9423, b: 1},    {r: 0.9826, g: 0.9348, b: 1},
    {r: 0.9699, g: 0.9273, b: 1},    {r: 0.9574, g: 0.9199, b: 1},
    {r: 0.9450, g: 0.9125, b: 1},    {r: 0.9328, g: 0.9053, b: 1},
    {r: 0.9208, g: 0.8980, b: 1},    {r: 0.9089, g: 0.8909, b: 1},
    {r: 0.8972, g: 0.8837, b: 1},    {r: 0.8856, g: 0.8767, b: 1},
    {r: 0.8742, g: 0.8697, b: 1},    {r: 0.8629, g: 0.8627, b: 1},
    {r: 0.8518, g: 0.8558, b: 1},    {r: 0.8408, g: 0.8490, b: 1},
    {r: 0.8300, g: 0.8422, b: 1},    {r: 0.8193, g: 0.8354, b: 1},
    {r: 0.8087, g: 0.8287, b: 1},    {r: 0.7983, g: 0.8221, b: 1},
    {r: 0.7880, g: 0.8155, b: 1},    {r: 0.7778, g: 0.8090, b: 1},
    {r: 0.7678, g: 0.8025, b: 1},    {r: 0.7579, g: 0.7960, b: 1},
    {r: 0.7481, g: 0.7896, b: 1},    {r: 0.7385, g: 0.7833, b: 1},
    {r: 0.7290, g: 0.7770, b: 1},    {r: 0.7196, g: 0.7708, b: 1},
    {r: 0.7103, g: 0.7646, b: 1},    {r: 0.7012, g: 0.7584, b: 1},
    {r: 0.6922, g: 0.7523, b: 1},    {r: 0.6832, g: 0.7463, b: 1},
    {r: 0.6745, g: 0.7403, b: 1},    {r: 0.6658, g: 0.7343, b: 1},
    {r: 0.6572, g: 0.7284, b: 1},    {r: 0.6488, g: 0.7226, b: 1},
    {r: 0.6405, g: 0.7167, b: 1},    {r: 0.6322, g: 0.7108, b: 1},
    {r: 0.6241, g: 0.7052, b: 1},    {r: 0.6161, g: 0.6996, b: 1},
    {r: 0.6082, g: 0.6939, b: 1},    {r: 0.6004, g: 0.6883, b: 1},
    {r: 0.5927, g: 0.6828, b: 1},    {r: 0.5851, g: 0.6773, b: 1},
    {r: 0.5777, g: 0.6718, b: 1},    {r: 0.5703, g: 0.6664, b: 1},
    {r: 0.5630, g: 0.6610, b: 1},    {r: 0.5558, g: 0.6556, b: 1},
    {r: 0.5487, g: 0.6503, b: 1},    {r: 0.5417, g: 0.6451, b: 1},
    {r: 0.5348, g: 0.6399, b: 1},    {r: 0.5280, g: 0.6347, b: 1},
    {r: 0.5213, g: 0.6296, b: 1},    {r: 0.5146, g: 0.6245, b: 1},
    {r: 0.5081, g: 0.6194, b: 1},    {r: 0.5016, g: 0.6144, b: 1},
    {r: 0.4953, g: 0.6094, b: 1},    {r: 0.4890, g: 0.6045, b: 1},
    {r: 0.4828, g: 0.5996, b: 1},    {r: 0.4767, g: 0.5948, b: 1},
    {r: 0.4707, g: 0.5900, b: 1},    {r: 0.4647, g: 0.5852, b: 1},
    {r: 0.4589, g: 0.5804, b: 1},    {r: 0.4531, g: 0.5757, b: 1},
    {r: 0.4474, g: 0.5711, b: 1},    {r: 0.4417, g: 0.5665, b: 1},
    {r: 0.4362, g: 0.5619, b: 1},    {r: 0.4307, g: 0.5573, b: 1},
    {r: 0.4253, g: 0.5528, b: 1},    {r: 0.4200, g: 0.5483, b: 1},
    {r: 0.4147, g: 0.5439, b: 1},    {r: 0.4094, g: 0.5395, b: 1},
    {r: 0.4044, g: 0.5351, b: 1},    {r: 0.3994, g: 0.5308, b: 1}
];


// Convert B-V color index to RGB color
export function bvToRGB(bv){
    const start=2;
    const finish=-0.4;
    
    if (typeof bv == 'undefined') return {r: 1, g: 1, b: 1};
    const colors = BVtoRGB_colors_WRec709;
    const range=Math.abs(finish-start);
    const step=colors.length/range;
    
    if(bv < 0.5) bv= finish - (finish - bv)/2; // make blue bluer..

    let i=Math.floor(colors.length-((bv-finish)*step));
    if(i>=colors.length) i=colors.length-1;
    if(i<0) i=0;    
    return colors[i];
}



// Convert B-V color index to RGB color
// This is approx, but colors are a bit blander
export function bvToRGB2(bv) {
    // Clamp B-V to [-0.4, 2.0]
    bv = Math.max(-0.4, Math.min(2.0, bv));

    let r = 0, g = 0, b = 0, t = 0;

    // Red component
    if (bv >= -0.4 && bv <= 0.0) {
        t = (bv + 0.4) / (0.0 + 0.4);
        r = 0.61 + (0.11 * t) + (0.1 * t * t);
    } else if (bv > 0.0 && bv <= 0.4) {
        t = (bv - 0.0) / (0.4 - 0.0);
        r = 0.83 + (0.17 * t);
    } else if (bv > 0.4 && bv <= 2.1) {
        t = (bv - 0.4) / (2.1 - 0.4);
        r = 1.0;
    }

    // Green component
    if (bv >= -0.4 && bv <= 0.0) {
        t = (bv + 0.4) / (0.0 + 0.4);
        g = 0.70 + (0.07 * t) + (0.1 * t * t);
    } else if (bv > 0.0 && bv <= 0.4) {
        t = (bv - 0.0) / (0.4 - 0.0);
        g = 0.87 + (0.11 * t);
    } else if (bv > 0.4 && bv <= 1.6) {
        t = (bv - 0.4) / (1.6 - 0.4);
        g = 0.98 - (0.16 * t);
    } else if (bv > 1.6 && bv <= 2.0) {
        t = (bv - 1.6) / (2.0 - 1.6);
        g = 0.82 - (0.5 * t * t);
    }

    // Blue component
    if (bv >= -0.4 && bv <= 0.4) {
        t = (bv + 0.4) / (0.4 + 0.4);
        b = 1.0;
    } else if (bv > 0.4 && bv <= 1.5) {
        t = (bv - 0.4) / (1.5 - 0.4);
        b = 1.0 - (0.47 * t) + (0.1 * t * t);
    } else if (bv > 1.5 && bv <= 1.94) {
        t = (bv - 1.5) / (1.94 - 1.5);
        b = 0.63 - (0.6 * t * t);
    }

    return { r, g, b };
}