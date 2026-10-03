    // PEC data capture: 100 buckets (pec position 0-99), each accumulating RA error samples
    let pecCaptureActive = false;
    let pecCaptureData = null;

    // Tracks the "starting interval" (whichever interval contains the position when capture began)
    // and measures it twice (once per lap) so row 0's baseline offset can be derived from the
    // difference between the two measurements.
    let pecTrackedIntervalStart = null;
    let pecCaptureDataLastBucket = 0;
    let pecCaptureDataBuckets = 0;

    let previousPECTable = null;

    let offsetError = 0;
    let offsetErrorCnt = 0;

    let PEC_TABLE_LENGTH = 50;        // 50 intervals
    const PEC_BUCKETS_PER_INTERVAL = 2; // 100 positions / 50 intervals
    const PEC_CAPTURE_TARGET_BUCKETS = 105; // buckets needed (100 + overlap) before capture is complete

    // Redraw the PEC chart overlay whenever the table is hand-edited in the textarea.
    document.addEventListener('DOMContentLoaded', () => {
        const pecTableTextArea = document.getElementById('pec_table_text');
        if (pecTableTextArea) {
            pecTableTextArea.addEventListener('change', () => updatePECChartOverlay());
        }
    });



    function pecTableToTextarea(pecTable) {
        const rows = [];
        for (let i = 0; i < pecTable.length; i++) {
            const [boundarySteps, correction] = pecTable[i];
            rows.push(`${boundarySteps},${correction}`);
        }
        document.getElementById('pec_table_text').value = rows.join('\n');
        updatePECChartOverlay();
    }

    // Draws the current pec_table_text as a semi-transparent stepped area on the PEC chart (datasets[1]),
    // normalized to the chart's 0-99 'PEC Progress' x-axis. Row 0's baseline offset (added to every
    // interval by the firmware) is folded into each bar's height so the overlay reflects the actual
    // correction that would be applied at each PEC position.
    function updatePECChartOverlay() {
        if (typeof pecChart === 'undefined' || !pecChart) return;

        const pecTable = parsePECTable();
        const points = [];
        if (pecTable.length >= 2) {
            const mspr = pecTable[pecTable.length - 1][0] || 1;
            const offset = pecTable[0][1] || 0;
            let prevX = 0;
            for (let i = 1; i < pecTable.length; i++) {
                const [boundarySteps, correction] = pecTable[i];
                const x = (boundarySteps / mspr) * 100;
                const y = correction + offset;
                points.push({ x: prevX, y });
                points.push({ x, y });
                prevX = x;
            }
        }

        pecChart.data.datasets[1].data = points;
        pecChart.update();
    }

    function createZeroPECTable(numrows) {
        // Reset the telescope to a zero PEC table before capturing, so measured errors aren't skewed
        // by a previously applied correction.
        const mspr = parseFloat(document.getElementById('pec_mspr').value) || 12000;
        const pec_size = parseInt(document.getElementById('pec_size').value) || 25;
        const intervals = pec_size;
        const microstepsPerInterval = mspr / intervals;
        const zeroRows = ['0,0'];
        for (let i = 1; i <= intervals; i++) {
            zeroRows.push(`${Math.round(i * microstepsPerInterval)},0`);
        }
        document.getElementById('pec_table_text').value = zeroRows.join('\n');
    }

    function startPECDataCapture() {
        resetCentroids(function() {
            pecCaptureData = Array.from({ length: 110 }, () => ({ sum: 0, count: 0, lastTimestamp: null }));
            pecTrackedIntervalStart = null;
            pecCaptureDataBuckets = 0;
            pecCaptureDataLastBucket = 0;
            pecCaptureActive = true;
            document.getElementById('pec_capture_running').textContent = ' is running... 0%';
            document.getElementById('pec_capture_running').classList.remove('hidden');
            receivePEC();
            renderPECAnalysisTable();
        });
    }

    // Called automatically once the starting interval has been measured twice.
    function finishPECDataCapture() {
        pecCaptureActive = false;
        document.getElementById('pec_capture_running').classList.add('hidden');
        renderPECAnalysisTable();
        generatePECCorrectionTable();
        alert('PEC analysis complete. Correction table generated.');
    }


    function _normalizePECTable(pecTable) {
        if (!Array.isArray(pecTable) || pecTable.length === 0) {
            return [];
        }
        
        let sumall = 0;
        for (let i = 1; i < pecTable.length; i++) {
            sumall += pecTable[i][1];
        }

        return pecTable.map(([microsteps, correction], index) => {
            if (index === 0) {
                return [microsteps, Math.round(correction+sumall/ (pecTable.length-1))];
            }
            return [microsteps, Math.round(correction - sumall / (pecTable.length-1))];
        });
    }

    function normalizePECTable() {
        const normalizedPECtable = _normalizePECTable(parsePECTable());
        pecTableToTextarea(normalizedPECtable);
    }

    // Where the jump between consecutive corrections exceeds 500, move 10% of the
    // larger (by magnitude) interval's value over to the smaller one, shrinking the spike.
    // Uses the original (unsmoothed) values for all diffs, so adjustments don't cascade.
    function _smoothPECTable(pecTable) {
        if (!Array.isArray(pecTable) || pecTable.length < 2) {
            return pecTable.map(row => [...row]);
        }

        const smoothed = pecTable.map(([microsteps, correction]) => [microsteps, correction]);

        for (let i = 0; i < pecTable.length - 1; i++) {
            const a = pecTable[i][1];
            const b = pecTable[i + 1][1];
            if (Math.abs(a - b) <= 500) continue;

            const aIsLarger = Math.abs(a) >= Math.abs(b);
            const adjust = (aIsLarger ? a : b) * 0.1;
            if (aIsLarger) {
                smoothed[i][1] -= adjust;
                smoothed[i + 1][1] += adjust;
            } else {
                smoothed[i + 1][1] -= adjust;
                smoothed[i][1] += adjust;
            }
        }

        return smoothed.map(([microsteps, correction]) => [microsteps, Math.round(correction)]);
    }

    function smoothPECTable() {
        const smoothedPECtable = _smoothPECTable(parsePECTable());
        pecTableToTextarea(smoothedPECtable);
    }


    function generateBoundariesAndOffset() {

        let bucketsPerInterval = Math.round(100 / PEC_TABLE_LENGTH); 
        const intervals = 100;

        // Row 0 offset: difference between the starting interval's error measured on lap 1 vs lap 2
        for (let i = 0; i < bucketsPerInterval; i++) {
            if(pecCaptureData[pecTrackedIntervalStart+i].count>0 && pecCaptureData[100+i].count>0) {
                offsetError += (pecCaptureData[pecTrackedIntervalStart+i].sum / pecCaptureData[pecTrackedIntervalStart+i].count) - (pecCaptureData[100+i].sum / pecCaptureData[100+i].count);
                offsetErrorCnt++;
            }
        }
        offsetError = offsetErrorCnt > 0 ? offsetError / offsetErrorCnt : 0;
        offsetErrorPerInterval = offsetError / intervals;


        for (let k = 0; k < intervals; k++) {
            const bucket = pecCaptureData[k];
            let err = bucket.count > 0 ? bucket.sum / bucket.count : 0;
            let intervals_between = k > pecTrackedIntervalStart ? k - pecTrackedIntervalStart : k - pecTrackedIntervalStart+intervals;
            err = err - offsetErrorPerInterval * intervals_between;
            pecCaptureData[k].correctedError = err;
        }
        putValuesOnChart(pecCaptureData);
    }


    function putValuesOnChart(pecCaptureData) {
        if (typeof pecChart === 'undefined' || !pecChart || !pecCaptureData) return;

        pecChart.data.datasets[0].data = [];
        for (let pos = 0; pos < pecCaptureData.length; pos++) {
            const y = pecCaptureData[pos].correctedError;
            if (y === undefined || isNaN(y)) continue;
            pecChart.data.datasets[0].data.push({ x: pos, y });
        }
        pecChart.update();
    }

    // Build the PEC correction table from the captured RA error data.
    // Row 0 is special: first column is literal 0, second column is a baseline offset
    // (microseconds/microstep) added by the firmware to every interval. It's derived from
    // measuring the starting interval's error twice (once per lap); the difference between
    // the two measurements is the drift accumulated over one full circle.
    // Rows 1-20: first column is the upper bound (in microsteps) of that interval
    // (MSPR/20, 2*MSPR/20, ..., MSPR for the last, 21st row). Second column is that
    // interval's correction (microseconds/microstep), with the offset subtracted out
    // since the firmware re-adds it when the table is applied.
    // Corrections are added on top of the table currently stored on the arduino, so
    // repeated PEC runs refine the table instead of discarding previous corrections.
    // New corrections are multiplied by attenuation_factor before being added to the previous table.
    

    // subtract the constant factor (offset) from the errors before calculating differences.
    // divide full circle error by number of intervals, then subtract per_interval_error*interval_index from each error.
    // otherwise the last interval will have a huge error compared to the others.

    // NOTE : ra arcsec errors are already corrected for declination. these are error in positioning, not image errors.

    const attenuationFactor = 0.5;

    function generatePECCorrectionTable() {
        previousPecTable = parsePECTable();
        const previousValues = previousPecTable.map(([, correction]) => Number(correction) || 0);

        generateBoundariesAndOffset();

        const mspr = parseFloat(document.getElementById('pec_mspr').value) || 12000;
        const rat = parseFloat(document.getElementById('pec_rat').value) || 144;

        const intervals = PEC_TABLE_LENGTH;
        let bucketsPerInterval = Math.round(100 / intervals); 
        const microstepsPerInterval = mspr / intervals;

        const siderealDaySeconds = 86164.0905;

        // angle (arcsec) covered by a single microstep at the equator: (360/RAT)/MSPR degrees * 3600
        const nominalArcsecPerMicrostep = 1296000 / (rat * mspr);
        // Nominal microseconds per microstep for correct sidereal tracking
        const baseMicrosecondsPerMicrostep = (siderealDaySeconds * 1e6) / (rat * mspr);

        // Average RA error (arcsec) sampled every 5 captured positions (21 boundary points, 0..100 wrapping to 0)
        const boundaryError = [];
        const firstInterval = pecTrackedIntervalStart/bucketsPerInterval;

        for (let k = 0; k <= intervals; k++) {
            const bucket = pecCaptureData[(k * bucketsPerInterval) % 100];
            if(bucket.count == 0) bucket=pecCaptureData[(k * bucketsPerInterval+1) % 100];
            let err = bucket.correctedError ? bucket.correctedError : (bucket.count > 0 ? bucket.correctedError / bucket.count : 0);
            let intervals_between = k > firstInterval ? k - firstInterval : k - firstInterval+intervals;
            err = err - offsetErrorPerInterval * intervals_between;
            boundaryError.push(err);
        }


        const fullCircleErrorArcsec = offsetErrorCnt > 0 ? offsetError / offsetErrorCnt : 0;
        const offsetMicrostepsEquivalent = fullCircleErrorArcsec / nominalArcsecPerMicrostep;
        const offset = (offsetMicrostepsEquivalent * baseMicrosecondsPerMicrostep) / mspr * attenuationFactor;

        const newPECtable = [];
        newPECtable.push([0, Math.round(offset + (previousValues[0] || 0))]);
        for (let i = 1; i <= intervals; i++) {
            const deltaArcsec = boundaryError[i - 1] - boundaryError[i];
            const microstepsEquivalent = deltaArcsec / nominalArcsecPerMicrostep;
            const totalCorrectionUs = microstepsEquivalent * baseMicrosecondsPerMicrostep;
            const correctionPerMicrostep = (totalCorrectionUs / microstepsPerInterval)*attenuationFactor;
            const boundarySteps = Math.round(i * microstepsPerInterval);
            newPECtable.push([boundarySteps, Math.round(correctionPerMicrostep + (previousValues[i] || 0))]);
        }
        pecTableToTextarea(newPECtable);
    }

    function renderPECAnalysisTable() {
        const tbody = document.getElementById('pec_analysis_tbody');
        if (!tbody) return;

        const rows = [];
        for (let pos = 0; pos < 100; pos++) {
            const bucket = pecCaptureData[pos];
            const avg = bucket.count > 0 ? bucket.sum / bucket.count : null;

            const prevPos = pos === 0 ? 99 : pos - 1;
            const prevBucket = pecCaptureData[prevPos];
            const prevAvg = prevBucket.count > 0 ? prevBucket.sum / prevBucket.count : null;
            const delta = (avg !== null && prevAvg !== null) ? avg - prevAvg : null;

            rows.push(`<tr><td>${pos}</td><td>${avg !== null ? avg.toFixed(2) : '-'}</td><td>${bucket.count}</td><td>${delta !== null ? delta.toFixed(2) : '-'}</td></tr>`);
        }
        tbody.innerHTML = rows.join('');
    }

    // Parses the pec_table_text textarea (lines of "boundarySteps,correction") into [boundarySteps, correction] pairs.
    function parsePECTable() {
        const pecTableText = document.getElementById('pec_table_text').value;
        const pecTable = [];
        pecTableText.split('\n').forEach(line => {
            const [x, y] = line.split(',').map(Number);
            if (!isNaN(x) && !isNaN(y)) {
                pecTable.push([x, y]);
            }
        });
        return pecTable;
    }

    // parse and prepare the PEC table from the textarea into linear array for sending to telescope
    function preparePECTable() {
        const pecTableText = document.getElementById('pec_table_text').value;
        const pecTable = [];
        pecTableText.split('\n').forEach(line => {
            const [x, y] = line.split(',').map(Number);
            if (!isNaN(x) && !isNaN(y)) {
                pecTable.push(x);
                pecTable.push(y);
            }
        });

        if (![22,42,52,102].includes(pecTable.length)) {
            alert("PEC table is empty or has an invalid length!");
            return [];
        }

        return pecTable;
    }

    function receivePEC() {
        fetch('/command_receivePEC', {
            method: 'GET'
        })
        .then(response => response.json())
        .then(data => {
            const pecTableText = document.getElementById('pec_table_text');
            if (data.status === 'success') {
                const pecTable = data.pec_table;
                const formattedTable = pecTable.map((value, index) => {
                    return index % 2 === 0 ? `${value},` : `${value}\n`;
                }).join('');
                pecTableText.value = formattedTable;
            } else {
                pecTableText.value = 'Error: ' + data.message;
            }
            previousPECTable = parsePECTable();
            PEC_TABLE_LENGTH = previousPECTable.length-1;
            document.getElementById('pec_size').value = PEC_TABLE_LENGTH;
            updatePECChartOverlay();
        })
        .catch((error) => {
            document.getElementById('pec_table_text').value = 'Error: ' + error;
        });
    }

    function sendPEC() {
        pec_table = preparePECTable();
        if (pec_table.length === 0) {
            return;
        }
        if (confirm("Are you sure you want to send PEC table to the Arduino?")) {   
            submitJSON('/command_sendPEC',
                { pec_table: pec_table }
            );
        }
    }

    // Save the pec_table_text textarea contents (boundarySteps,correction rows) as a CSV file.
    function savePECTable() {
        const text = document.getElementById('pec_table_text').value;
        const blob = new Blob([text], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'pec_table.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    // Load a PEC table CSV/TSV file (boundarySteps,correction rows) into the pec_table_text textarea.
    // Separator can be comma or TAB.
    function loadPECTable(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const rows = [];
            e.target.result.split('\n').forEach(line => {
                const trimmed = line.trim();
                if (!trimmed) return;

                const parts = trimmed.split(/[,\t]/).map(s => s.trim());
                const boundarySteps = Number(parts[0]);
                const correction = Number(parts[1]);
                if (isNaN(boundarySteps) || isNaN(correction)) return;

                rows.push(`${boundarySteps},${correction}`);
            });

            document.getElementById('pec_table_text').value = rows.join('\n');
            updatePECChartOverlay();
        };
        reader.readAsText(file);
        event.target.value = '';
    }



        function savePECdata(data) {
        // Save PEC data capture sample: pec position, RA error and timestamp
        if (pecCaptureActive && data.pec_position !== undefined && data.last_correction.ra_arcsec !== undefined) {
            const pos = Math.round(Number(data.pec_position));
            if (!isNaN(pos) && pos >= 0 && pos <= 99) {

                // The "starting interval" is whichever interval contains the position when capture began.
                if (pecTrackedIntervalStart === null) {
                    // We want to fully capture the first interval buckets, so return if we're not at the start of an interval.
                    if(pos % PEC_BUCKETS_PER_INTERVAL !== 0) return;
                    pecTrackedIntervalStart = pos;
                    pecCaptureDataLastBucket = pecTrackedIntervalStart;
                    resetChart();
                }

                var bucket = null;
                if (pos >= pecTrackedIntervalStart && pecCaptureDataBuckets >= 100) {
                    // overflow data goes into the extra 10 buckets at the end of the array
                    bucket = pecCaptureData[100 + (pos-pecTrackedIntervalStart)];
                } else {
                    bucket = pecCaptureData[pos];
                }
                bucket.sum += data.last_correction.ra_arcsec;
                bucket.count += 1;
                bucket.lastTimestamp = Date.now();
                if(pos !== pecCaptureDataLastBucket) {
                    pecCaptureDataBuckets += pos>pecCaptureDataLastBucket ? pos-pecCaptureDataLastBucket : pos+1;
                    pecCaptureDataLastBucket = pos;
                }

                const percent = Math.min(100, Math.round(pecCaptureDataBuckets / PEC_CAPTURE_TARGET_BUCKETS * 100));
                document.getElementById('pec_capture_running').textContent = ` is running... ${percent}%`;

                if (pecCaptureDataBuckets >= PEC_CAPTURE_TARGET_BUCKETS) {
                    finishPECDataCapture();
                }

                renderPECAnalysisTable();
            }
        }   
    }


    // Load PEC analysis data (pos,avg,count,delta) from a CSV/TSV file, reconstructing sum/count buckets.
    // Only avg is trusted (count is treated as 1 per row); delta is derived on render.
    // Separator can be comma or TAB.
    function loadPECAnalysisData(event) {
        const file = event.target.files[0];
        if (!file) return;

        const reader = new FileReader();
        reader.onload = (e) => {
            const newData = Array.from({ length: 110 }, () => ({ sum: 0, count: 0, lastTimestamp: null }));

            e.target.result.split('\n').forEach(line => {
                const trimmed = line.trim();
                if (!trimmed) return;

                const parts = trimmed.split(/[,\t]/).map(s => s.trim());
                const pos = Number(parts[0]);
                const avg = Number(parts[1]);
                if (isNaN(pos) || pos < 0 || pos > 109 || isNaN(avg)) return; // skips header row too

                newData[pos] = { sum: avg, count: 1, lastTimestamp: null };
            });

            pecCaptureData = newData;
            pecCaptureActive = false;
            renderPECAnalysisTable();
        };
        reader.readAsText(file);
        event.target.value = '';
    }

        // Save the currently captured PEC analysis data (pos, avg, count, delta) as a CSV file.
    function savePECAnalysisData() {
        if (!pecCaptureData) {
            alert('No PEC analysis data to save.');
            return;
        }

        const lines = ['pos,avg,count,delta'];
        for (let pos = 0; pos < 110; pos++) {
            const bucket = pecCaptureData[pos];
            const avg = bucket.count > 0 ? bucket.sum / bucket.count : '';

            const prevPos = pos === 0 ? 99 : pos - 1;
            const prevBucket = pecCaptureData[prevPos];
            const prevAvg = prevBucket.count > 0 ? prevBucket.sum / prevBucket.count : null;
            const delta = (bucket.count > 0 && prevAvg !== null) ? (avg - prevAvg) : '';

            lines.push(`${pos},${avg},${bucket.count},${delta}`);
        }

        const blob = new Blob([lines.join('\n')], { type: 'text/csv' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'pec_analysis.csv';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }
