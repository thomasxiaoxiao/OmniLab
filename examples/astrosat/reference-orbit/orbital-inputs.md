# Reference orbital inputs for a scoped AstroSat model check

This is a curated input record, not a second scientific paper or an observational dataset.
The official PyEphem quick reference supplies the following IRIDIUM 80 two-line elements and Boston observer example:
https://rhodesmill.org/pyephem/quick.html
The full retrieved HTML is archived as quick.html with SHA-256 ab9fc38315d4d9f2b5a4aa8f0d16923c1eea4de9daa0497ce07167444472058f. Retrieved 2026-10-04T03:21:11.224214+00:00.

IRIDIUM 80 [+]
1 25469U 98051C   09119.61415140 -.00000218  00000-0 -84793-4 0  4781
2 25469  86.4029 183.4052 0002522  86.7221 273.4294 14.34215064557061

The documentation starts the next-pass search at 2009/5/1 UTC. Boston is provided by ephem.city('Boston'), a bundled offline city database: latitude 42:21:30.4, longitude -71:03:35.2, elevation 15.338848 m. Setting pressure=0 removes atmospheric refraction for an explicitly chosen geometrical model. PyEphem 4.2.1 computes the first pass maximum at 2009-05-01T00:26:32.950313Z. The archived availability-probe.json sampled -60 through +60 seconds around that peak in 10-second steps: all 13 samples were above the horizon and not eclipsed. This setup probe computed geometry only, not brightness or test outcomes. The first-pass edges are partly eclipsed, and the pass has low elevation (peak about 4.35 degrees); these are limitations, not errors to hide. The published quick-reference rise-time example differs from the current pinned dependency's output; do not force its old timestamp as a numerical target.

The IRIDIUM TLE is a historical public reference input near its 2009 epoch. It is NOT the paper's 2021 Starlink sample, a validated observed light curve, or a current orbital prediction. Do not claim reproduction of the paper's main result or Iridium flare physics. Any assumed optical cross-section and seed-dependent timing uncertainty are explicit synthetic sensitivity assumptions, not measured satellite properties. The authors' diffuse-sphere brightness option can be compared with the paper's constant-phase approximation as a limited model sensitivity test; neither is ground truth for this satellite.

The upstream AstroSat process_satellite method can use real ephem.Observer, ephem.readtle, ephem.Sun and satellite.compute. No fabricated satellite positions or mock solar objects are necessary. The repository's stellar-catalog and plotting paths require other packages and remain out of scope. Keep original numerical method bodies unchanged.
