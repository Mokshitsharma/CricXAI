/**
 * CricXAI — Tactical Ground Engine & Fielder Visualizer (v2)
 * Renders an authentic international cricket ground with all 11 players,
 * country-wise bowler & batsman filtering, realistic fielder names, customizable presets,
 * RHB/LHB mirroring, and 2D/3D views.
 */

const FIELD_PRESET_DEFINITIONS = {
  powerplay_attack: {
    label: "Powerplay Attack",
    description: "Aggressive slip cordon + tight infield ring to choke singles and induce outside edges.",
    positions: [
      { id: "slip", name: "slip", label: "1st Slip", x: 0.66, y: 0.78, type: "slip", prob: "92%", speed: "0.32s", dist: "14.2m", role: "Elite slip reflex; guards thick outside edge." },
      { id: "second_slip", name: "second_slip", label: "2nd Slip", x: 0.70, y: 0.76, type: "slip", prob: "89%", speed: "0.35s", dist: "16.8m", role: "Catches flying edges off moving delivery." },
      { id: "gully", name: "gully", label: "Gully", x: 0.76, y: 0.70, type: "slip", prob: "90%", speed: "0.33s", dist: "21.5m", role: "Covers aerial cut and thick drive deflection." },
      { id: "point", name: "point", label: "Backward Point", x: 0.85, y: 0.55, type: "infield", prob: "96%", speed: "0.28s", dist: "25.0m", role: "Gun fielder; cuts off square cut singles & direct hits." },
      { id: "cover", name: "cover", label: "Extra Cover", x: 0.78, y: 0.40, type: "infield", prob: "94%", speed: "0.30s", dist: "24.5m", role: "Intercepts off-drive; pressures batsman with fast returns." },
      { id: "mid_off", name: "mid_off", label: "Mid-off", x: 0.58, y: 0.25, type: "infield", prob: "91%", speed: "0.37s", dist: "22.0m", role: "Tight on single, saves straight drive." },
      { id: "mid_on", name: "mid_on", label: "Mid-on", x: 0.42, y: 0.25, type: "infield", prob: "93%", speed: "0.36s", dist: "22.5m", role: "Anticipates on-drive; athletic diving range." },
      { id: "mid_wicket", name: "mid_wicket", label: "Mid-wicket", x: 0.28, y: 0.45, type: "infield", prob: "91%", speed: "0.34s", dist: "26.0m", role: "Catches mistimed flick against incoming angle." },
      { id: "fine_leg", name: "fine_leg", label: "Fine Leg", x: 0.30, y: 0.85, type: "outfield", prob: "86%", speed: "0.41s", dist: "62.0m", role: "Boundary rider for top-edge hooks and glances." }
    ]
  },
  middle_containment: {
    label: "Middle-Overs Containment",
    description: "Balanced 5-4 field with deep boundaries protecting square boundaries while squeezing the inner ring.",
    positions: [
      { id: "slip", name: "slip", label: "1st Slip", x: 0.66, y: 0.78, type: "slip", prob: "92%", speed: "0.32s", dist: "14.2m", role: "Keeps pressure on tentative defensive push." },
      { id: "point", name: "point", label: "Point", x: 0.86, y: 0.52, type: "infield", prob: "96%", speed: "0.28s", dist: "26.5m", role: "Patrols point region; saves 1-2 runs every over." },
      { id: "cover", name: "cover", label: "Cover", x: 0.76, y: 0.40, type: "infield", prob: "94%", speed: "0.30s", dist: "24.5m", role: "Guards the off-side driving channel." },
      { id: "mid_off", name: "mid_off", label: "Mid-off", x: 0.58, y: 0.22, type: "infield", prob: "91%", speed: "0.37s", dist: "23.0m", role: "Backs up bowler and saves straight single." },
      { id: "mid_on", name: "mid_on", label: "Mid-on", x: 0.42, y: 0.22, type: "infield", prob: "93%", speed: "0.36s", dist: "23.0m", role: "Covers bowler's non-striker side." },
      { id: "mid_wicket", name: "mid_wicket", label: "Mid-wicket", x: 0.24, y: 0.44, type: "infield", prob: "91%", speed: "0.34s", dist: "27.0m", role: "Chokes the easy rotating single to mid-wicket." },
      { id: "deep_mid_wicket", name: "deep_mid_wicket", label: "Deep Mid-wicket", x: 0.16, y: 0.80, type: "outfield", prob: "93%", speed: "0.36s", dist: "68.0m", role: "Deep boundary rider for aerial pulls and slog-sweeps." },
      { id: "deep_square_leg", name: "deep_square_leg", label: "Deep Square Leg", x: 0.14, y: 0.62, type: "outfield", prob: "88%", speed: "0.39s", dist: "65.5m", role: "Sweeps the leg boundary for pulls." },
      { id: "long_off", name: "long_off", label: "Long-off", x: 0.56, y: 0.05, type: "outfield", prob: "89%", speed: "0.39s", dist: "72.0m", role: "Boundary guard for lofted straight drives." }
    ]
  },
  death_yorker_ring: {
    label: "Death Yorker Ring",
    description: "Optimized for yorker execution at the death. Outfielders straight and deep square; ring tight to save 2s.",
    positions: [
      { id: "short_third", name: "short_third", label: "Short Third", x: 0.78, y: 0.72, type: "infield", prob: "87%", speed: "0.39s", dist: "20.5m", role: "Catches squirts and toe-edges off yorkers." },
      { id: "point", name: "point", label: "Backward Point", x: 0.86, y: 0.52, type: "infield", prob: "96%", speed: "0.28s", dist: "26.5m", role: "Locks down backward point singles." },
      { id: "deep_cover", name: "deep_cover", label: "Deep Cover", x: 0.84, y: 0.12, type: "outfield", prob: "89%", speed: "0.37s", dist: "68.0m", role: "Protects extra-cover boundary against slices." },
      { id: "long_off", name: "long_off", label: "Long-off", x: 0.56, y: 0.04, type: "outfield", prob: "89%", speed: "0.39s", dist: "74.0m", role: "Prevents six down the ground off full balls." },
      { id: "long_on", name: "long_on", label: "Long-on", x: 0.44, y: 0.04, type: "outfield", prob: "90%", speed: "0.38s", dist: "74.0m", role: "Protects long boundary off heaves." },
      { id: "deep_mid_wicket", name: "deep_mid_wicket", label: "Deep Mid-wicket", x: 0.16, y: 0.80, type: "outfield", prob: "93%", speed: "0.36s", dist: "68.0m", role: "Hotspot for death overs catch chances." },
      { id: "deep_square_leg", name: "deep_square_leg", label: "Deep Square Leg", x: 0.12, y: 0.60, type: "outfield", prob: "88%", speed: "0.39s", dist: "66.0m", role: "Boundary cushion protector." },
      { id: "mid_off", name: "mid_off", label: "Mid-off (Up)", x: 0.58, y: 0.24, type: "infield", prob: "91%", speed: "0.37s", dist: "22.0m", role: "Inside ring to prevent easy single to long-off." },
      { id: "mid_on", name: "mid_on", label: "Mid-on (Up)", x: 0.42, y: 0.24, type: "infield", prob: "93%", speed: "0.36s", dist: "22.5m", role: "Inside ring to deny the tap-and-run." }
    ]
  },
  short_ball_trap: {
    label: "Short-Ball Trap",
    description: "Designed for bouncers & bodyline bowling. Double boundary catchers on the leg side with short mid-wicket.",
    positions: [
      { id: "fine_leg_back", name: "fine_leg_back", label: "Deep Fine Leg", x: 0.30, y: 0.92, type: "outfield", prob: "87%", speed: "0.41s", dist: "70.0m", role: "Top-edge hook boundary catcher right on the rope." },
      { id: "deep_square_leg", name: "deep_square_leg", label: "Deep Square Leg", x: 0.12, y: 0.58, type: "outfield", prob: "88%", speed: "0.39s", dist: "66.0m", role: "Primary target for mistimed pull shots." },
      { id: "deep_mid_wicket", name: "deep_mid_wicket", label: "Deep Mid-wicket", x: 0.16, y: 0.78, type: "outfield", prob: "93%", speed: "0.36s", dist: "68.0m", role: "Catches high swirling mistimed pulls." },
      { id: "short_mid_wicket", name: "short_mid_wicket", label: "Short Mid-wicket", x: 0.30, y: 0.44, type: "infield", prob: "90%", speed: "0.32s", dist: "18.0m", role: "Catches mistimed fends & shoulder-of-bat pops." },
      { id: "point", name: "point", label: "Backward Point", x: 0.86, y: 0.52, type: "infield", prob: "96%", speed: "0.28s", dist: "26.5m", role: "Catches uppish square cuts over point." },
      { id: "third", name: "third", label: "Third Man", x: 0.80, y: 0.80, type: "outfield", prob: "88%", speed: "0.40s", dist: "64.0m", role: "Covers ramp and uppercut deflections." },
      { id: "mid_off", name: "mid_off", label: "Mid-off", x: 0.58, y: 0.24, type: "infield", prob: "91%", speed: "0.37s", dist: "22.0m", role: "Holds position on off-drive." },
      { id: "mid_on", name: "mid_on", label: "Mid-on", x: 0.42, y: 0.24, type: "infield", prob: "93%", speed: "0.36s", dist: "22.5m", role: "Prevents drop-and-run on the leg-side." },
      { id: "long_on", name: "long_on", label: "Long-on", x: 0.44, y: 0.06, type: "outfield", prob: "90%", speed: "0.38s", dist: "71.0m", role: "Protects deep straight boundary." }
    ]
  },
  fourth_stump_catchers: {
    label: "Fourth-Stump Catchers",
    description: "Full outswing / seam attack with 3 slips and gully in a tight cordon to capture outside edges.",
    positions: [
      { id: "slip", name: "slip", label: "1st Slip", x: 0.66, y: 0.78, type: "slip", prob: "92%", speed: "0.32s", dist: "14.2m", role: "Anchors the slip cordon right beside keeper." },
      { id: "second_slip", name: "second_slip", label: "2nd Slip", x: 0.70, y: 0.76, type: "slip", prob: "89%", speed: "0.35s", dist: "16.8m", role: "Catches deflected outside edges." },
      { id: "third_slip", name: "third_slip", label: "3rd Slip", x: 0.74, y: 0.74, type: "slip", prob: "88%", speed: "0.36s", dist: "19.0m", role: "Wider slip; catches thick drive snicks." },
      { id: "gully", name: "gully", label: "Gully", x: 0.80, y: 0.68, type: "slip", prob: "90%", speed: "0.33s", dist: "22.0m", role: "Flying gully for high-handed sliced edges." },
      { id: "point", name: "point", label: "Cover Point", x: 0.86, y: 0.52, type: "infield", prob: "96%", speed: "0.28s", dist: "26.5m", role: "Athletic ring fielder; chokes the off-side." },
      { id: "cover", name: "cover", label: "Extra Cover", x: 0.76, y: 0.40, type: "infield", prob: "94%", speed: "0.30s", dist: "24.5m", role: "Pressures batsman pushing away from body." },
      { id: "mid_off", name: "mid_off", label: "Mid-off", x: 0.58, y: 0.24, type: "infield", prob: "91%", speed: "0.37s", dist: "22.0m", role: "Standard mid-off; guards straight single." },
      { id: "mid_on", name: "mid_on", label: "Mid-on", x: 0.42, y: 0.24, type: "infield", prob: "93%", speed: "0.36s", dist: "22.5m", role: "Mid-on saves straight nudge." },
      { id: "mid_wicket", name: "mid_wicket", label: "Mid-wicket", x: 0.26, y: 0.46, type: "infield", prob: "91%", speed: "0.34s", dist: "27.0m", role: "Solitary leg-side ring fielder." }
    ]
  },
  spin_in_out: {
    label: "Spin In-Out",
    description: "Close-in catcher at silly point and slip paired with deep boundary riders for mistimed lofted hits.",
    positions: [
      { id: "slip", name: "slip", label: "1st Slip", x: 0.66, y: 0.78, type: "slip", prob: "92%", speed: "0.32s", dist: "13.8m", role: "Sharply attentive for sharp turn and edge." },
      { id: "silly_point", name: "silly_point", label: "Silly Point", x: 0.62, y: 0.66, type: "slip", prob: "86%", speed: "0.25s", dist: "4.5m", role: "Right under the batsman's bat; catches bat-pad pops." },
      { id: "point", name: "point", label: "Point", x: 0.86, y: 0.52, type: "infield", prob: "96%", speed: "0.28s", dist: "26.5m", role: "Cuts off reverse sweep & square drive." },
      { id: "deep_cover", name: "deep_cover", label: "Deep Cover", x: 0.82, y: 0.12, type: "outfield", prob: "89%", speed: "0.37s", dist: "67.0m", role: "Boundary rider for lofted inside-out strokes." },
      { id: "long_off", name: "long_off", label: "Long-off", x: 0.56, y: 0.05, type: "outfield", prob: "89%", speed: "0.39s", dist: "73.0m", role: "Deep straight boundary cover." },
      { id: "long_on", name: "long_on", label: "Long-on", x: 0.44, y: 0.05, type: "outfield", prob: "90%", speed: "0.38s", dist: "73.0m", role: "Catches step-out straight hits." },
      { id: "deep_mid_wicket", name: "deep_mid_wicket", label: "Deep Mid-wicket", x: 0.16, y: 0.78, type: "outfield", prob: "93%", speed: "0.36s", dist: "68.0m", role: "Key target for mistimed slog-sweep." },
      { id: "short_mid_wicket", name: "short_mid_wicket", label: "Short Mid-wicket", x: 0.30, y: 0.46, type: "infield", prob: "90%", speed: "0.32s", dist: "17.5m", role: "Catches leading edge on forward defense." },
      { id: "deep_square_leg", name: "deep_square_leg", label: "Deep Square Leg", x: 0.12, y: 0.60, type: "outfield", prob: "88%", speed: "0.39s", dist: "66.0m", role: "Protects sweep shot to the boundary." }
    ]
  }
};

class CricketGroundManager {
  constructor(options = {}) {
    this.container = document.getElementById(options.containerId || "groundArena");
    this.svg = document.getElementById(options.svgId || "groundSvg");
    this.presetKey = options.initialPreset || "death_yorker_ring";
    this.isLeftHanded = false;
    this.is3D = true;
    this.selectedFielderId = "point";
    
    // Country & Player selections
    this.bowlingCountry = options.bowlingCountry || "India";
    this.battingCountry = options.battingCountry || "Australia";
    this.currentBowlerName = "J. Bumrah";
    this.currentBowlerStyle = "pace_right_arm";
    this.currentStrikerName = "Steve Smith";
    this.currentKeeperName = "KL Rahul";

    this.init();
  }

  init() {
    this.updateCountrySquads();
    this.renderBaseGround();
    this.renderPlayers();
    this.bindEvents();
    this.updateInspector(this.getSelectedFielder());
  }

  setBowlingCountry(country) {
    this.bowlingCountry = country;
    this.updateCountrySquads();
    this.renderPlayers();
  }

  setBattingCountry(country) {
    this.battingCountry = country;
    this.updateCountrySquads();
    this.renderPlayers();
  }

  setBowler(name, style = "pace_right_arm") {
    this.currentBowlerName = name;
    this.currentBowlerStyle = style;
    this.renderPlayers();
  }

  setStriker(name, isLHB = false) {
    this.currentStrikerName = name;
    this.isLeftHanded = isLHB;
    this.renderBaseGround();
    this.renderPlayers();
  }

  setPreset(key) {
    if (FIELD_PRESET_DEFINITIONS[key]) {
      this.presetKey = key;
      this.renderPlayers();
      const first = this.getCurrentPositions()[0];
      if (first) {
        this.selectFielder(first.id);
      }
    }
  }

  toggleHand(isLHB) {
    this.isLeftHanded = isLHB;
    this.renderBaseGround();
    this.renderPlayers();
  }

  toggle3D(enable3D) {
    this.is3D = enable3D;
    if (this.container) {
      this.container.classList.toggle("mode-3d", this.is3D);
    }
  }

  updateCountrySquads() {
    if (!window.CricXData) return;
    const bowlSquad = window.CricXData.getPlayersByCountry(this.bowlingCountry);
    const batSquad = window.CricXData.getPlayersByCountry(this.battingCountry);

    // Pick top bowler
    const bowler = bowlSquad.find(p => p.type === "bowler") || bowlSquad[2] || bowlSquad[0];
    if (bowler) {
      this.currentBowlerName = bowler.name;
      this.currentBowlerStyle = bowler.bowlingStyle || "pace_right_arm";
    }

    // Pick wicketkeeper
    const keeper = bowlSquad.find(p => p.role.toLowerCase().includes("wicketkeeper")) || bowlSquad[4] || bowlSquad[0];
    if (keeper) {
      this.currentKeeperName = keeper.name;
    }

    // Pick striker
    const striker = batSquad.find(p => p.type === "batsman") || batSquad[0];
    if (striker) {
      this.currentStrikerName = striker.name;
      this.isLeftHanded = striker.battingHand === "LHB";
    }
  }

  getFielderNameForIndex(index) {
    if (!window.CricXData) return "Fielder " + (index + 1);
    const squad = window.CricXData.getPlayersByCountry(this.bowlingCountry);
    // Filter out active bowler & keeper to assign fielders
    const fielders = squad.filter(p => p.name !== this.currentBowlerName && p.name !== this.currentKeeperName);
    if (fielders[index]) {
      const parts = fielders[index].name.split(" ");
      return parts.length > 1 ? `${parts[0][0]}. ${parts.slice(1).join(" ")}` : fielders[index].name;
    }
    return "Fielder " + (index + 1);
  }

  getCurrentPositions() {
    const preset = FIELD_PRESET_DEFINITIONS[this.presetKey] || FIELD_PRESET_DEFINITIONS.death_yorker_ring;
    return preset.positions.map((p, idx) => {
      const effectiveX = this.isLeftHanded ? (1.0 - p.x) : p.x;
      return {
        ...p,
        effectiveX,
        effectiveY: p.y,
        player: this.getFielderNameForIndex(idx)
      };
    });
  }

  getSelectedFielder() {
    const positions = this.getCurrentPositions();
    return positions.find(p => p.id === this.selectedFielderId) || positions[0];
  }

  selectFielder(id) {
    this.selectedFielderId = id;
    this.updateFielderHighlights();
    const f = this.getSelectedFielder();
    if (f) this.updateInspector(f);
  }

  renderBaseGround() {
    if (!this.svg) return;
    const offText = this.isLeftHanded ? "LEG SIDE" : "OFF SIDE";
    const legText = this.isLeftHanded ? "OFF SIDE" : "LEG SIDE";

    const baseHtml = `
      <defs>
        <radialGradient id="turfGradient" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="#1b4d36" />
          <stop offset="55%" stop-color="#143d2b" />
          <stop offset="90%" stop-color="#0e2a1e" />
          <stop offset="100%" stop-color="#081b13" />
        </radialGradient>

        <linearGradient id="pitchTexture" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#c4ab80"/>
          <stop offset="25%" stop-color="#a89269"/>
          <stop offset="70%" stop-color="#bf9f73"/>
          <stop offset="100%" stop-color="#b09265"/>
        </linearGradient>

        <filter id="glowFielder" x="-50%" y="-50%" width="200%" height="200%">
          <feDropShadow dx="0" dy="2" stdDeviation="4" flood-color="#00E676" flood-opacity="0.6"/>
        </filter>
      </defs>

      <!-- Main Oval Ground Grass Turf -->
      <ellipse cx="300" cy="290" rx="275" ry="265" fill="url(#turfGradient)" stroke="#22543d" stroke-width="3"/>
      
      <!-- Lawn Mower Ring Stripes -->
      <ellipse cx="300" cy="290" rx="245" ry="235" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="14"/>
      <ellipse cx="300" cy="290" rx="205" ry="195" fill="none" stroke="rgba(0,0,0,0.12)" stroke-width="14"/>
      <ellipse cx="300" cy="290" rx="165" ry="155" fill="none" stroke="rgba(255,255,255,0.03)" stroke-width="12"/>

      <!-- Boundary Rope and Cushions -->
      <ellipse cx="300" cy="290" rx="270" ry="260" fill="none" stroke="#FFFFFF" stroke-width="2.5" stroke-dasharray="14 6" opacity="0.85"/>

      <!-- 30-Yard Fielding Restriction Circle -->
      <ellipse cx="300" cy="290" rx="145" ry="140" fill="none" stroke="#00E676" stroke-width="1.8" stroke-dasharray="6 6" opacity="0.65"/>
      <text x="300" y="142" fill="#34D399" font-family="'JetBrains Mono', monospace" font-size="8.5" font-weight="600" text-anchor="middle" letter-spacing="1">30-YARD RESTRICTION CIRCLE</text>

      <!-- Off/Leg Side Indicators -->
      <text x="545" y="295" fill="rgba(255,255,255,0.3)" font-family="'Plus Jakarta Sans', sans-serif" font-size="10" font-weight="800" text-anchor="end" letter-spacing="1.5">${offText}</text>
      <text x="55" y="295" fill="rgba(255,255,255,0.3)" font-family="'Plus Jakarta Sans', sans-serif" font-size="10" font-weight="800" text-anchor="start" letter-spacing="1.5">${legText}</text>

      <!-- Anticipated Scoring Danger Cone (Wagon Wheel overlay) -->
      <path d="${this.isLeftHanded ? 'M 300 355 L 110 220 A 240 230 0 0 1 180 120 Z' : 'M 300 355 L 490 220 A 240 230 0 0 0 420 120 Z'}" 
            fill="rgba(245, 158, 11, 0.08)" stroke="rgba(245, 158, 11, 0.35)" stroke-dasharray="4 4"/>
      <text x="${this.isLeftHanded ? 160 : 440}" y="180" fill="#F59E0B" font-family="'JetBrains Mono', monospace" font-size="8" font-weight="600" opacity="0.8">ATTACK CORRIDOR</text>

      <!-- Central 22-Yard Pitch Strip -->
      <g id="pitchStrip">
        <rect x="282" y="200" width="36" height="180" rx="4" fill="url(#pitchTexture)" stroke="#8c704b" stroke-width="1.5" filter="drop-shadow(0 4px 10px rgba(0,0,0,0.6))"/>
        
        <!-- White Crease Markings -->
        <line x1="272" y1="355" x2="328" y2="355" stroke="#FFFFFF" stroke-width="2"/>
        <line x1="282" y1="365" x2="318" y2="365" stroke="#FFFFFF" stroke-width="1.5"/>
        <line x1="276" y1="345" x2="276" y2="370" stroke="#FFFFFF" stroke-width="1.5"/>
        <line x1="324" y1="345" x2="324" y2="370" stroke="#FFFFFF" stroke-width="1.5"/>

        <!-- Striker Stumps -->
        <circle cx="295" cy="365" r="2.2" fill="#e5e7eb"/>
        <circle cx="300" cy="365" r="2.2" fill="#e5e7eb"/>
        <circle cx="305" cy="365" r="2.2" fill="#e5e7eb"/>
        <line x1="293" y1="365" x2="307" y2="365" stroke="#f59e0b" stroke-width="1.2"/>

        <!-- Bowler popping crease -->
        <line x1="272" y1="225" x2="328" y2="225" stroke="#FFFFFF" stroke-width="2"/>
        <line x1="282" y1="215" x2="318" y2="215" stroke="#FFFFFF" stroke-width="1.5"/>
        <line x1="276" y1="210" x2="276" y2="235" stroke="#FFFFFF" stroke-width="1.5"/>
        <line x1="324" y1="210" x2="324" y2="235" stroke="#FFFFFF" stroke-width="1.5"/>

        <!-- Non-striker Stumps -->
        <circle cx="295" cy="215" r="2.2" fill="#e5e7eb"/>
        <circle cx="300" cy="215" r="2.2" fill="#e5e7eb"/>
        <circle cx="305" cy="215" r="2.2" fill="#e5e7eb"/>
        <line x1="293" y1="215" x2="307" y2="215" stroke="#f59e0b" stroke-width="1.2"/>
      </g>

      <!-- Dynamic Players Layer -->
      <g id="playersLayer"></g>
    `;

    this.svg.innerHTML = baseHtml;
  }

  renderPlayers() {
    const layer = this.svg.querySelector("#playersLayer");
    if (!layer) return;

    const positions = this.getCurrentPositions();
    const bowlTheme = window.CricXData ? window.CricXData.getJerseyTheme(this.bowlingCountry) : { primary: "#00E676", secondary: "#10B981" };
    const batTheme = window.CricXData ? window.CricXData.getJerseyTheme(this.battingCountry) : { primary: "#EAB308", secondary: "#FEF08A" };
    let playersHtml = "";

    // 1. Wicket Keeper
    playersHtml += `
      <g class="fixed-player keeper" transform="translate(300, 388)">
        <circle cx="0" cy="0" r="9" fill="${bowlTheme.primary}" stroke="${bowlTheme.secondary}" stroke-width="2" filter="drop-shadow(0 2px 5px rgba(0,0,0,0.8))"/>
        <text x="0" y="3" font-family="'Plus Jakarta Sans', sans-serif" font-size="7" font-weight="800" fill="#FFFFFF" text-anchor="middle">WK</text>
        <rect x="-38" y="11" width="76" height="15" rx="4" fill="rgba(8,16,14,0.94)" stroke="rgba(56,189,248,0.4)" stroke-width="1"/>
        <text x="0" y="22" font-family="'Plus Jakarta Sans', sans-serif" font-size="7.5" font-weight="700" fill="#FFFFFF" text-anchor="middle">${this.currentKeeperName} (WK)</text>
      </g>
    `;

    // 2. Bowler
    playersHtml += `
      <g class="fixed-player bowler" transform="translate(300, 192)">
        <circle cx="0" cy="0" r="9" fill="${bowlTheme.secondary}" stroke="${bowlTheme.primary}" stroke-width="2" filter="drop-shadow(0 2px 5px rgba(0,0,0,0.8))"/>
        <text x="0" y="3" font-family="'Plus Jakarta Sans', sans-serif" font-size="7" font-weight="800" fill="#FFFFFF" text-anchor="middle">BW</text>
        <line x1="0" y1="-18" x2="0" y2="-4" stroke="#F87171" stroke-width="1.8"/>
        <rect x="-44" y="-34" width="88" height="15" rx="4" fill="rgba(8,16,14,0.94)" stroke="rgba(248,113,113,0.4)" stroke-width="1"/>
        <text x="0" y="-23" font-family="'Plus Jakarta Sans', sans-serif" font-size="7.5" font-weight="700" fill="#FFFFFF" text-anchor="middle">${this.currentBowlerName} (Bowler)</text>
      </g>
    `;

    // 3. Striker Batsman
    const strikerOffset = this.isLeftHanded ? 12 : -12;
    playersHtml += `
      <g class="fixed-player striker" transform="translate(${300 + strikerOffset}, 355)">
        <circle cx="0" cy="0" r="7.5" fill="${batTheme.primary}" stroke="${batTheme.secondary}" stroke-width="1.8"/>
        <rect x="-44" y="-20" width="88" height="14" rx="3" fill="rgba(8,16,14,0.94)" stroke="rgba(234,179,8,0.5)" stroke-width="1"/>
        <text x="0" y="-10" font-family="'Plus Jakarta Sans', sans-serif" font-size="7.5" font-weight="700" fill="#FEF08A" text-anchor="middle">${this.currentStrikerName} (${this.isLeftHanded ? 'LHB' : 'RHB'})</text>
      </g>
    `;

    // 4. Non-Striker Batsman
    playersHtml += `
      <g class="fixed-player non-striker" transform="translate(318, 225)">
        <circle cx="0" cy="0" r="6" fill="#71717A" stroke="#D4D4D8" stroke-width="1"/>
      </g>
    `;

    // 5. The 9 Tactical Fielders with Names & Positions
    positions.forEach((f) => {
      const svgX = 50 + f.effectiveX * 500;
      const svgY = 40 + f.effectiveY * 500;
      const isSelected = f.id === this.selectedFielderId;
      
      let badgeColor = bowlTheme.primary;
      if (f.type === "slip") badgeColor = bowlTheme.secondary;
      else if (f.type === "outfield") badgeColor = bowlTheme.border || bowlTheme.text;

      playersHtml += `
        <g class="fielder-pin-group ${isSelected ? 'selected' : ''}" 
           data-id="${f.id}" 
           transform="translate(${svgX.toFixed(1)}, ${svgY.toFixed(1)})"
           onclick="window.cricketGround.selectFielder('${f.id}')">
          
          ${isSelected ? `
            <circle cx="0" cy="0" r="17" fill="none" stroke="${badgeColor}" stroke-width="1.8" opacity="0.9">
              <animate attributeName="r" values="12;20;12" dur="2s" repeatCount="indefinite"/>
              <animate attributeName="opacity" values="1;0.2;1" dur="2s" repeatCount="indefinite"/>
            </circle>
          ` : ''}

          <circle class="fielder-pin-bg" cx="0" cy="0" r="${isSelected ? 10 : 8.5}" 
                  fill="${badgeColor}" stroke="#FFFFFF" stroke-width="1.6" filter="url(#glowFielder)"/>
          
          <text x="0" y="3" font-family="'Plus Jakarta Sans', sans-serif" font-size="7" font-weight="800" fill="#04140c" text-anchor="middle">
            ${f.label.slice(0, 1)}
          </text>

          <g transform="translate(0, ${svgY > 480 ? -28 : 13})">
            <rect x="-44" y="0" width="88" height="23" rx="5" 
                  fill="rgba(7, 14, 11, 0.94)" stroke="${isSelected ? badgeColor : 'rgba(255,255,255,0.18)'}" stroke-width="${isSelected ? 1.5 : 1}" 
                  filter="drop-shadow(0 4px 10px rgba(0,0,0,0.8))"/>
            <text class="fielder-label-text" x="0" y="10">${f.player}</text>
            <text class="fielder-sub-pos" x="0" y="19">${f.label}</text>
          </g>
        </g>
      `;
    });

    layer.innerHTML = playersHtml;
    this.updateRosterList();
  }

  updateInspector(f) {
    if (!f) return;
    const nameEl = document.getElementById("insFielderName");
    const posEl = document.getElementById("insFielderPos");
    const avatarEl = document.getElementById("insFielderAvatar");
    const distEl = document.getElementById("insFielderDist");
    const probEl = document.getElementById("insFielderProb");
    const speedEl = document.getElementById("insFielderSpeed");
    const roleEl = document.getElementById("insFielderRole");

    if (nameEl) nameEl.textContent = f.player;
    if (posEl) posEl.textContent = f.label.toUpperCase() + ` (${f.type.toUpperCase()})`;
    if (avatarEl) avatarEl.textContent = f.player.split(" ").map(w => w[0]).join("");
    if (distEl) distEl.textContent = f.dist;
    if (probEl) probEl.textContent = f.prob;
    if (speedEl) speedEl.textContent = f.speed;
    if (roleEl) roleEl.textContent = f.role;
  }

  updateFielderHighlights() {
    const layer = this.svg.querySelector("#playersLayer");
    if (!layer) return;
    layer.querySelectorAll(".fielder-pin-group").forEach(el => {
      const isSel = el.dataset.id === this.selectedFielderId;
      el.classList.toggle("selected", isSel);
    });
    this.updateRosterList();
  }

  updateRosterList() {
    const list = document.getElementById("fielderRosterList");
    if (!list) return;

    const positions = this.getCurrentPositions();
    list.innerHTML = positions.map(f => {
      const isSel = f.id === this.selectedFielderId;
      return `
        <div class="roster-item ${isSel ? 'active' : ''}" onclick="window.cricketGround.selectFielder('${f.id}')">
          <div style="display:flex; align-items:center; gap:8px;">
            <span style="font-family:var(--font-mono); font-size:11px; font-weight:700; color:${isSel ? 'var(--accent-green)' : 'var(--text-muted)'}">${f.label}</span>
            <span style="font-weight:600; color:var(--text-primary); font-size:12.5px;">${f.player}</span>
          </div>
          <span style="font-family:var(--font-mono); font-size:11px; color:var(--accent-mint);">${f.dist}</span>
        </div>
      `;
    }).join("");
  }

  bindEvents() {
    const presetSelect = document.getElementById("groundPresetSelect");
    if (presetSelect) {
      presetSelect.value = this.presetKey;
      presetSelect.addEventListener("change", (e) => {
        this.setPreset(e.target.value);
      });
    }

    const btn2D = document.getElementById("btnView2D");
    const btn3D = document.getElementById("btnView3D");
    if (btn2D && btn3D) {
      btn2D.onclick = () => {
        btn2D.classList.add("active");
        btn3D.classList.remove("active");
        this.toggle3D(false);
      };
      btn3D.onclick = () => {
        btn3D.classList.add("active");
        btn2D.classList.remove("active");
        this.toggle3D(true);
      };
    }

    const btnRHB = document.getElementById("btnBatterRHB");
    const btnLHB = document.getElementById("btnBatterLHB");
    if (btnRHB && btnLHB) {
      btnRHB.onclick = () => {
        btnRHB.classList.add("active");
        btnLHB.classList.remove("active");
        this.toggleHand(false);
      };
      btnLHB.onclick = () => {
        btnLHB.classList.add("active");
        btnRHB.classList.remove("active");
        this.toggleHand(true);
      };
    }
  }
}

window.CricketGroundManager = CricketGroundManager;
