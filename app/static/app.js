/* ── Skool Video Downloader – Frontend ────────────────────────────── */

const App = {
  jobs: [],
  selectedJobId: null,
  settings: {},
  pollTimer: null,
  extractedVideos: [],

  // ── Init ───────────────────────────────────────────────────────
  async init() {
    await this.loadSettings();
    await this.loadJobs();
    this.startPolling();
    this.updateAuthStatus();

    // Enter key on URL input
    document.getElementById('urlInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') this.startDownload();
    });
  },

  // ── API helpers ────────────────────────────────────────────────
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

  // ── Auth status ────────────────────────────────────────────────
  updateAuthStatus() {
    const el = document.getElementById('authStatus');
    const cookie = this.settings.cookie_display || '';
    if (cookie) {
      el.className = 'auth-status connected';
      el.textContent = 'Cookie set';
    } else {
      el.className = 'auth-status disconnected';
      el.textContent = 'No cookie';
    }
  },

  // ── Jobs ───────────────────────────────────────────────────────
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
    this.pollTimer = setInterval(() => this.loadJobs(), 1500);
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

    let html = '';
    for (const job of this.jobs) {
      const active = job.id === this.selectedJobId ? ' active' : '';
      const badge = this.badgeHTML(job.status);
      const name = job.title || job.id;
      const time = this.formatTime(job.created_at);
      const progress = job.progress || 0;
      const progressClass = job.status === 'done' ? ' done' : job.status === 'failed' ? ' failed' : '';
      const showProgress = ['downloading', 'done', 'failed'].includes(job.status);

      html += `
        <div class="job-card${active}" data-id="${job.id}" onclick="App.selectJob('${job.id}')">
          <div class="job-name">${this.esc(name)}</div>
          <div class="job-meta">
            ${badge}
            <span>${time}</span>
            ${job.file_size ? `<span>${this.esc(job.file_size)}</span>` : ''}
          </div>
          ${showProgress ? `
          <div class="progress-bar-wrap">
            <div class="progress-bar${progressClass}" style="width:${progress}%"></div>
          </div>` : ''}
        </div>`;
    }
    const scrollTop = list.scrollTop;
    list.innerHTML = html;
    list.scrollTop = scrollTop;
  },

  badgeHTML(status) {
    const labels = {
      queued: 'Queued',
      extracting: 'Extracting',
      downloading: 'Downloading',
      done: 'Done',
      failed: 'Failed',
    };
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

  // ── Select job ─────────────────────────────────────────────────
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
    const progress = job.progress || 0;
    const progressClass = job.status === 'done' ? ' done' : job.status === 'failed' ? ' failed' : '';

    let errorBox = '';
    if (job.error) {
      errorBox = `<div class="error-box">${this.esc(job.error)}</div>`;
    }

    let successBox = '';
    if (job.status === 'done' && job.output_path) {
      successBox = `
        <div class="success-box">
          Download complete! Saved to:<br>
          <strong>${this.esc(job.output_path)}</strong>
        </div>`;
    }

    let progressBar = '';
    if (['extracting', 'downloading'].includes(job.status)) {
      progressBar = `
        <div class="big-progress">
          <div class="big-progress-bar-wrap">
            <div class="big-progress-bar${progressClass}" style="width:${progress}%"></div>
          </div>
          <div class="big-progress-text">${this.esc(job.progress_text || 'Working...')}</div>
        </div>`;
    } else if (job.status === 'done') {
      progressBar = `
        <div class="big-progress">
          <div class="big-progress-bar-wrap">
            <div class="big-progress-bar done" style="width:100%"></div>
          </div>
          <div class="big-progress-text">Complete</div>
        </div>`;
    } else if (job.status === 'failed') {
      progressBar = `
        <div class="big-progress">
          <div class="big-progress-bar-wrap">
            <div class="big-progress-bar failed" style="width:100%"></div>
          </div>
          <div class="big-progress-text">Failed</div>
        </div>`;
    }

    content.innerHTML = `
      <div class="detail-header">
        <h2>${this.esc(job.title || 'Untitled')}</h2>
        ${statusBadge}
        <div style="margin-left:auto">
          <button class="btn btn-danger btn-sm" onclick="App.deleteJob('${job.id}')">Delete</button>
        </div>
      </div>

      ${errorBox}
      ${successBox}
      ${progressBar}

      <div class="detail-grid">
        <div class="detail-card">
          <h3>Download Info</h3>
          <div class="info-row"><span class="label">Status:</span><span class="value">${this.esc(job.status)}</span></div>
          <div class="info-row"><span class="label">Quality:</span><span class="value">${this.esc(this.settings.video_quality || 'best')}</span></div>
          ${job.file_size ? `<div class="info-row"><span class="label">File Size:</span><span class="value">${this.esc(job.file_size)}</span></div>` : ''}
          <div class="info-row"><span class="label">Created:</span><span class="value">${job.created_at ? new Date(job.created_at).toLocaleString() : '-'}</span></div>
          ${job.finished_at ? `<div class="info-row"><span class="label">Finished:</span><span class="value">${new Date(job.finished_at).toLocaleString()}</span></div>` : ''}
        </div>

        <div class="detail-card">
          <h3>URLs</h3>
          <div class="info-row"><span class="label">Page:</span><span class="value" style="font-size:11px">${this.esc(job.url)}</span></div>
          ${job.video_url ? `<div class="info-row"><span class="label">Video:</span><span class="value" style="font-size:11px">${this.esc(job.video_url)}</span></div>` : ''}
        </div>

        ${job.output_path ? `
        <div class="detail-card full-width">
          <h3>Output</h3>
          <div class="info-row"><span class="label">Saved to:</span><span class="value" style="font-size:11px">${this.esc(job.output_path)}</span></div>
        </div>` : ''}
      </div>`;
  },

  // ── Actions ────────────────────────────────────────────────────
  async startDownload() {
    const input = document.getElementById('urlInput');
    const url = input.value.trim();
    if (!url) return;

    try {
      const res = await this.api('/download', {
        method: 'POST',
        body: JSON.stringify({ url }),
      });
      this.selectedJobId = res.job_id;
      input.value = '';
      await this.loadJobs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  },

  async extractInfo() {
    const input = document.getElementById('urlInput');
    const url = input.value.trim();
    if (!url) return;

    document.getElementById('extractContent').innerHTML = '<p style="color:var(--text-dim)">Extracting...</p>';
    document.getElementById('extractModal').classList.add('open');

    try {
      const res = await this.api('/extract', {
        method: 'POST',
        body: JSON.stringify({ url }),
      });

      this.extractedVideos = res.videos || [];

      let html = `<div class="extract-result">
        <h3>${this.esc(res.title || 'Unknown')}</h3>
        <p style="font-size:12px;color:var(--text-dim);margin-bottom:12px">${this.esc(url)}</p>`;

      if (this.extractedVideos.length === 0) {
        html += '<p style="color:var(--yellow)">No videos found on this page. Make sure you have a valid cookie set.</p>';
      } else {
        for (let i = 0; i < this.extractedVideos.length; i++) {
          const v = this.extractedVideos[i];
          html += `
            <div class="extract-item">
              <input type="checkbox" id="ev_${i}" checked>
              <span class="type-badge">${this.esc(v.type)}</span>
              <span class="url">${this.esc(v.url)}</span>
            </div>`;
        }
      }
      html += '</div>';
      document.getElementById('extractContent').innerHTML = html;
      document.getElementById('extractDownloadBtn').style.display = this.extractedVideos.length ? '' : 'none';
    } catch (e) {
      document.getElementById('extractContent').innerHTML = `<div class="error-box">${this.esc(e.message)}</div>`;
    }
  },

  async downloadExtracted() {
    const urls = [];
    for (let i = 0; i < this.extractedVideos.length; i++) {
      const cb = document.getElementById(`ev_${i}`);
      if (cb && cb.checked) {
        urls.push({ url: this.extractedVideos[i].url });
      }
    }
    if (urls.length === 0) return;

    try {
      await this.api('/download/batch', {
        method: 'POST',
        body: JSON.stringify({ urls }),
      });
      this.closeExtract();
      document.getElementById('urlInput').value = '';
      await this.loadJobs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  },

  closeExtract() {
    document.getElementById('extractModal').classList.remove('open');
  },

  async deleteJob(jobId) {
    try {
      await this.api(`/jobs/${jobId}`, { method: 'DELETE' });
      if (this.selectedJobId === jobId) this.selectedJobId = null;
      await this.loadJobs();
    } catch (e) {
      alert('Error: ' + e.message);
    }
  },

  async clearCompleted() {
    const done = this.jobs.filter(j => j.status === 'done' || j.status === 'failed');
    for (const j of done) {
      try {
        await this.api(`/jobs/${j.id}`, { method: 'DELETE' });
      } catch (e) { /* ignore */ }
    }
    if (done.find(j => j.id === this.selectedJobId)) {
      this.selectedJobId = null;
    }
    await this.loadJobs();
  },

  // ── Settings ───────────────────────────────────────────────────
  async loadSettings() {
    try {
      this.settings = await this.api('/settings');
    } catch (e) {
      console.error('Failed to load settings:', e);
    }
  },

  openSettings() {
    const s = this.settings;
    document.getElementById('s_cookie').value = s.cookie || '';
    document.getElementById('s_download_path').value = s.download_path || '';
    document.getElementById('s_video_quality').value = s.video_quality || 'best';
    document.getElementById('s_filename_template').value = s.filename_template || '{title}';
    document.getElementById('settingsModal').classList.add('open');
  },

  closeSettings() {
    document.getElementById('settingsModal').classList.remove('open');
  },

  async saveSettings() {
    const patch = {
      download_path: document.getElementById('s_download_path').value,
      video_quality: document.getElementById('s_video_quality').value,
      filename_template: document.getElementById('s_filename_template').value,
    };

    // Only include cookie if it was changed (not the masked version)
    const cookieVal = document.getElementById('s_cookie').value.trim();
    if (cookieVal) {
      patch.cookie = cookieVal;
    }

    try {
      this.settings = await this.api('/settings', {
        method: 'PATCH',
        body: JSON.stringify(patch),
      });
      this.updateAuthStatus();
      this.closeSettings();
    } catch (e) {
      alert('Failed to save settings: ' + e.message);
    }
  },
};

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
