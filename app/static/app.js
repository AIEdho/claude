/* ── Image Factory – Frontend ─────────────────────────────────────── */

const App = {
  jobs: [],
  selectedJobId: null,
  settings: {},
  pollTimer: null,

  // ── Init ─────────────────────────────────────────────────────────
  async init() {
    await this.loadSettings();
    await this.loadJobs();
    this.startPolling();
    this.setupFileInput();
    // Update watcher toggle
    document.getElementById('watcherToggle').checked = this.settings.watcher_enabled || false;
  },

  // ── API helpers ──────────────────────────────────────────────────
  async api(url, opts = {}) {
    try {
      const res = await fetch(url, {
        headers: { 'Content-Type': 'application/json', ...opts.headers },
        ...opts,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || res.statusText);
      }
      return res.json();
    } catch (e) {
      console.error(`API error [${url}]:`, e);
      throw e;
    }
  },

  // ── Jobs ─────────────────────────────────────────────────────────
  async loadJobs() {
    try {
      this.jobs = await this.api('/jobs');
      this.renderJobsList();
      if (this.selectedJobId) this.renderDetail();
    } catch (e) {
      console.error('Failed to load jobs:', e);
    }
  },

  startPolling() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => this.loadJobs(), 2000);
  },

  renderJobsList() {
    const list = document.getElementById('jobsList');
    const empty = document.getElementById('jobsEmpty');

    if (this.jobs.length === 0) {
      empty.style.display = 'block';
      list.querySelectorAll('.job-card').forEach(el => el.remove());
      return;
    }
    empty.style.display = 'none';

    // Build HTML
    let html = '';
    for (const job of this.jobs) {
      const active = job.id === this.selectedJobId ? ' active' : '';
      const badge = this.badgeHTML(job.status);
      const name = job.original_filename || job.id;
      const time = this.formatTime(job.created_at);
      const needsAction = job.needs_bg_decision ? ' &middot; <span style="color:var(--yellow)">Needs decision</span>' : '';
      html += `
        <div class="job-card${active}" data-id="${job.id}" onclick="App.selectJob('${job.id}')">
          <div class="job-name">${this.esc(name)}</div>
          <div class="job-meta">${badge} <span>${time}</span>${needsAction}</div>
        </div>`;
    }
    // Preserve scroll position
    const scrollTop = list.scrollTop;
    list.innerHTML = html;
    list.scrollTop = scrollTop;
  },

  badgeHTML(status) {
    const labels = { queued: 'Queued', processing: 'Processing', done: 'Done', failed: 'Failed' };
    return `<span class="badge ${status}">${labels[status] || status}</span>`;
  },

  formatTime(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  },

  esc(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  },

  // ── Select job ───────────────────────────────────────────────────
  selectJob(id) {
    this.selectedJobId = id;
    this.renderJobsList();
    this.renderDetail();
  },

  renderDetail() {
    const job = this.jobs.find(j => j.id === this.selectedJobId);
    const content = document.getElementById('detailContent');
    const empty = document.getElementById('detailEmpty');

    if (!job) {
      content.style.display = 'none';
      empty.style.display = 'flex';
      return;
    }
    content.style.display = 'block';
    empty.style.display = 'none';

    const statusBadge = this.badgeHTML(job.status);

    // Decision banner
    let decisionBanner = '';
    if (job.needs_bg_decision && job.status === 'queued') {
      decisionBanner = `
        <div class="decision-banner">
          <div class="msg">This image needs a background removal decision before processing.</div>
          <button class="btn btn-success btn-sm" onclick="App.decideBg('${job.id}', true)">Remove Background</button>
          <button class="btn btn-secondary btn-sm" onclick="App.decideBg('${job.id}', false)">Skip / Keep</button>
        </div>`;
    }

    // Error box
    let errorBox = '';
    if (job.error) {
      errorBox = `<div class="error-box">Error: ${this.esc(job.error)}</div>`;
    }

    // Steps
    const stepNames = {
      detect: 'Detect File Type',
      background_removal: 'Background Removal',
      edge_cleanup: 'Edge Cleanup',
      upscale: 'Upscale',
      resize: 'Resize to Preset',
      export: 'Export',
    };
    let stepsHTML = '';
    for (const [key, label] of Object.entries(stepNames)) {
      const st = job.steps[key] || 'pending';
      const icons = {
        pending: '&middot;',
        running: '&#9654;',
        done: '&#10003;',
        skipped: '&#8211;',
        failed: '&#10007;',
      };
      stepsHTML += `<li><span class="step-icon ${st}">${icons[st]}</span> ${label}</li>`;
    }

    // Settings used
    const preset = this.settings.presets?.[job.preset];
    const presetLabel = preset ? preset.label : job.preset;

    // Outputs
    let outputsHTML = '<div style="color:var(--text-dim);font-size:13px">No outputs yet</div>';
    if (job.output_files && job.output_files.length > 0) {
      outputsHTML = job.output_files.map(f => {
        const name = f.split('/').pop().split('\\').pop();
        return `<div class="output-item"><span style="color:var(--green)">&#10003;</span> ${this.esc(name)}</div>`;
      }).join('');
    }

    content.innerHTML = `
      <div class="detail-header">
        <h2>${this.esc(job.original_filename)}</h2>
        ${statusBadge}
        <div class="detail-actions">
          <button class="btn btn-secondary btn-sm" onclick="App.rerunJob('${job.id}')">Re-run</button>
          <button class="btn btn-secondary btn-sm" onclick="App.duplicateJob('${job.id}')">Duplicate</button>
        </div>
      </div>

      ${decisionBanner}
      ${errorBox}

      <div class="detail-grid">
        <div class="detail-card">
          <h3>Processing Steps</h3>
          <ul class="step-list">${stepsHTML}</ul>
        </div>

        <div class="detail-card">
          <h3>Job Settings</h3>
          <div class="info-row"><span class="label">Preset:</span><span class="value">${this.esc(presetLabel)}</span></div>
          <div class="info-row"><span class="label">BG Mode:</span><span class="value">${this.esc(job.background_mode)}</span></div>
          <div class="info-row"><span class="label">Upscale:</span><span class="value">${this.esc(job.upscale_quality)}</span></div>
          <div class="info-row"><span class="label">Fit:</span><span class="value">${this.esc(job.fit_mode)}</span></div>
          <div class="info-row"><span class="label">JPG:</span><span class="value">${job.export_jpg ? 'Yes' : 'No'}</span></div>
          <div class="info-row"><span class="label">Transparent:</span><span class="value">${job.has_transparency === null ? 'Pending' : job.has_transparency ? 'Yes' : 'No'}</span></div>
        </div>

        <div class="detail-card">
          <h3>Outputs</h3>
          ${outputsHTML}
        </div>

        <div class="detail-card">
          <h3>Info</h3>
          <div class="info-row"><span class="label">Job ID:</span><span class="value" style="font-size:11px">${this.esc(job.id)}</span></div>
          <div class="info-row"><span class="label">Input:</span><span class="value" style="font-size:11px">${this.esc(job.input_path)}</span></div>
          <div class="info-row"><span class="label">Created:</span><span class="value">${job.created_at ? new Date(job.created_at).toLocaleString() : '-'}</span></div>
          <div class="info-row"><span class="label">Finished:</span><span class="value">${job.finished_at ? new Date(job.finished_at).toLocaleString() : '-'}</span></div>
        </div>
      </div>`;
  },

  // ── Actions ──────────────────────────────────────────────────────
  async decideBg(jobId, remove) {
    try {
      await this.api(`/jobs/${jobId}/decide-bg?remove=${remove}`, { method: 'POST' });
      await this.loadJobs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  },

  async rerunJob(jobId) {
    try {
      const res = await this.api(`/jobs/${jobId}/rerun`, { method: 'POST' });
      this.selectedJobId = res.job_id;
      await this.loadJobs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  },

  async duplicateJob(jobId) {
    const presetKey = prompt('Enter preset key (leave blank for same):', '');
    try {
      const body = {};
      if (presetKey) body.preset = presetKey;
      const res = await this.api(`/jobs/${jobId}/duplicate`, {
        method: 'POST',
        body: JSON.stringify(body),
      });
      this.selectedJobId = res.job_id;
      await this.loadJobs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  },

  // ── File import ──────────────────────────────────────────────────
  setupFileInput() {
    const input = document.getElementById('fileInput');
    input.addEventListener('change', async (e) => {
      const file = e.target.files[0];
      if (!file) return;

      const formData = new FormData();
      formData.append('file', file);

      try {
        const res = await fetch('/import', { method: 'POST', body: formData });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || 'Upload failed');
        }
        const data = await res.json();
        this.selectedJobId = data.job_id;
        await this.loadJobs();
      } catch (e) {
        alert('Import error: ' + e.message);
      }
      input.value = '';
    });
  },

  // ── Folder links ─────────────────────────────────────────────────
  openFolder(which) {
    // Show the path to the user (can't open OS folders from browser)
    const paths = {
      inbox: this.settings.inbox_path,
      output: this.settings.output_path,
    };
    const p = paths[which] || '';
    alert(`${which.toUpperCase()} folder path:\n\n${p}\n\nOpen this path in your file explorer.`);
  },

  // ── Watcher toggle ──────────────────────────────────────────────
  async toggleWatcher(enabled) {
    try {
      if (enabled) {
        await this.api('/watcher/start', { method: 'POST' });
      } else {
        await this.api('/watcher/stop', { method: 'POST' });
      }
    } catch (e) {
      alert('Error toggling watcher: ' + e.message);
      document.getElementById('watcherToggle').checked = !enabled;
    }
  },

  // ── Settings ─────────────────────────────────────────────────────
  async loadSettings() {
    try {
      this.settings = await this.api('/settings');
    } catch (e) {
      console.error('Failed to load settings:', e);
    }
  },

  openSettings() {
    const s = this.settings;
    document.getElementById('s_inbox_path').value = s.inbox_path || '';
    document.getElementById('s_output_path').value = s.output_path || '';
    document.getElementById('s_archive_path').value = s.archive_path || '';
    document.getElementById('s_logs_path').value = s.logs_path || '';
    document.getElementById('s_background_removal').value = s.background_removal || 'ask';
    document.getElementById('s_upscale_quality').value = s.upscale_quality || 'fast';
    document.getElementById('s_fit_mode').value = s.fit_mode || 'pad';
    document.getElementById('s_export_jpg_preview').value = String(s.export_jpg_preview || false);
    document.getElementById('s_naming_template').value = s.naming_template || '';
    document.getElementById('s_watcher_stability_seconds').value = s.watcher_stability_seconds || 4;
    document.getElementById('s_watcher_trigger_mode').value = String(s.watcher_trigger_mode || false);

    // Populate presets dropdown
    const presetSelect = document.getElementById('s_selected_preset');
    presetSelect.innerHTML = '';
    if (s.presets) {
      for (const [key, p] of Object.entries(s.presets)) {
        const opt = document.createElement('option');
        opt.value = key;
        opt.textContent = p.label;
        if (key === s.selected_preset) opt.selected = true;
        presetSelect.appendChild(opt);
      }
    }

    document.getElementById('settingsModal').classList.add('open');
  },

  closeSettings() {
    document.getElementById('settingsModal').classList.remove('open');
  },

  async saveSettings() {
    const patch = {
      inbox_path: document.getElementById('s_inbox_path').value,
      output_path: document.getElementById('s_output_path').value,
      archive_path: document.getElementById('s_archive_path').value,
      logs_path: document.getElementById('s_logs_path').value,
      background_removal: document.getElementById('s_background_removal').value,
      upscale_quality: document.getElementById('s_upscale_quality').value,
      fit_mode: document.getElementById('s_fit_mode').value,
      export_jpg_preview: document.getElementById('s_export_jpg_preview').value === 'true',
      naming_template: document.getElementById('s_naming_template').value,
      selected_preset: document.getElementById('s_selected_preset').value,
      watcher_stability_seconds: parseInt(document.getElementById('s_watcher_stability_seconds').value) || 4,
      watcher_trigger_mode: document.getElementById('s_watcher_trigger_mode').value === 'true',
    };

    try {
      this.settings = await this.api('/settings', {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      this.closeSettings();
    } catch (e) {
      alert('Failed to save settings: ' + e.message);
    }
  },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
