/**
 * Fetches a DSS image URL from STScI DSS Archive for given RA and Dec
 * @param {string} ra - Right Ascension (e.g., '11:34.3', '11h34m3s')
 * @param {string} dec - Declination (e.g., '+48:57', '+48d57m')
 * @returns {Promise<string>} - URL of the DSS image (GIF format)
 * @throws {Error} - If RA/Dec is invalid, server fails, or image is unavailable
 */
export async function getImageDSS(ra, dec) {

    // Validate inputs
    if (!validateRA(ra)) {
        throw new Error(`Invalid RA format: ${ra}`);
    }
    if (!validateDEC(dec)) {
        throw new Error(`Invalid Dec format: ${dec}`);
    }

    const url = getImageDSSUrl(ra, dec);

    console.log(`Fetching DSS image: ${url}`);

    try {
        // Verify the URL returns a valid image
        const response = await fetch(url, {
            method: 'HEAD',
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/91.0.4472.124'
            }
        });

        if (!response.ok) {
            throw new Error(`DSS server returned status ${response.status}`);
        }

        return url;
    } catch (error) {
        if (error.message.includes('404')) {
            throw new Error(`No DSS image found for RA=${ra}, Dec=${dec}`);
        } else if (error.message.includes('timeout')) {
            throw new Error(`Request timed out for ${url}`);
        } else {
            throw new Error(`Failed to fetch DSS image: ${error.message}`);
        }
    }
}


export function getImageDSSUrl(ra, dec, widthArcmin = 60, heightArcmin = 60) {


    // Construct DSS query URL
    const baseUrl = 'https://archive.stsci.edu/cgi-bin/dss_search';
    const params = {
        r: ra,                      // RA (e.g., '11:34:13')
        d: dec,                     // Dec (e.g., '+48*57:12')
        e: 'J2000',                // Epoch
        h: widthArcmin,                     // Height (arcminutes)
        w: heightArcmin,                     // Width (arcminutes)
        f: 'GIF',                  // Format
        c: 'none',                 // Compression
        //v: 'poss2ukstu_red'        // Survey (DSS2 Red)
    };

    const queryString = Object.entries(params)
        .map(([key, value]) => `${key}=${encodeURIComponent(value)}`)
        .join('&');
    return `${baseUrl}?${queryString}`;
}

function validateRA(ra) {
    const raPattern = /^[0-2][0-9]:[0-5][0-9]:[0-5][0-9]$/;
    return raPattern.test(ra);
}

function validateDEC(dec) {
    const decPattern = /^[+-][0-9][0-9]\*[0-5][0-9]:[0-5][0-9]$/;
    return decPattern.test(dec);
}


/**
 * Uploads an array of catalog objects as a JSON string to catalog.json via PUT request
 * @param {Array} imageCatalog - Array of [ra, dec, name, texture, mesh, rotation]
 * @param {string} [serverUrl='https://192.168.1.16:8443'] - Server URL
 * @returns {Promise<string>} - Success message or throws error
 */
export async function uploadCatalogAsJson(imageCatalog, serverUrl = 'https://192.168.1.16:8443') {
    // Validate input
    if (!Array.isArray(imageCatalog) || imageCatalog.length === 0) {
        throw new Error('imageCatalog must be a non-empty array');
    }

    // Extract ra, dec, name, rotation
    const catalogData = imageCatalog.map((entry, index) => {
        if (!Array.isArray(entry) || entry.length < 6) {
            console.warn(`Invalid catalog entry at index ${index}: ${JSON.stringify(entry)}`);
            return null;
        }
        const [ra, dec, name, , , rotation] = entry;
        if (typeof ra !== 'string' || typeof dec !== 'string' || typeof name !== 'string') {
            console.warn(`Invalid types at index ${index}: ra=${ra}, dec=${dec}, name=${name}`);
            return null;
        }
        return { ra, dec, name, rotation: typeof rotation === 'number' ? rotation : 0 };
    }).filter(entry => entry !== null);

    if (catalogData.length === 0) {
        throw new Error('No valid catalog entries found');
    }

    // Convert to JSON string
    const jsonString = JSON.stringify(catalogData, null, 2); // Pretty-print with 2 spaces

    // Upload via PUT
    try {
        const response = await fetch(`${serverUrl}/catalog.json`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
                'Content-Length': jsonString.length
            },
            body: jsonString
        });

        if (!response.ok) {
            throw new Error(`Server responded with status ${response.status}: ${await response.text()}`);
        }

        const responseText = await response.text();
        console.log(`Uploaded catalog.json: ${responseText}`);
        return `Successfully uploaded ${catalogData.length} entries to catalog.json`;
    } catch (error) {
        console.error(`Failed to upload catalog.json: ${error.message}`);
        throw new Error(`Upload failed: ${error.message}`);
    }
}

