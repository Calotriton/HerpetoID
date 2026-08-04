// Pulls release information straight from the GitHub API, so publishing a release on GitHub is the
// only step needed to update the download page. No site edit, no rebuild.
(function () {
  var repo = document.body.dataset.repo;
  if (!repo) return;

  var api = 'https://api.github.com/repos/' + repo + '/releases';
  var latestBox = document.getElementById('latest-release');
  var historyBox = document.getElementById('release-history');

  function formatSize(bytes) {
    if (!bytes) return '';
    var mb = bytes / (1024 * 1024);
    return mb >= 1024 ? (mb / 1024).toFixed(1) + ' GB' : Math.round(mb) + ' MB';
  }

  function formatDate(iso) {
    return new Date(iso).toLocaleDateString(undefined, { year: 'numeric', month: 'long', day: 'numeric' });
  }

  function escapeHtml(value) {
    var div = document.createElement('div');
    div.textContent = value;
    return div.innerHTML;
  }

  function renderNoRelease() {
    latestBox.innerHTML =
      '<div class="release-head"><h2>No public release yet</h2></div>' +
      '<p class="muted">HerpetoID is in early development and the first packaged Windows build has not ' +
      'been published yet. Watch the repository to be notified the moment it lands — or run it from ' +
      'source today using the instructions below.</p>' +
      '<p><a class="btn btn-secondary" href="https://github.com/' + repo + '" rel="noopener">Watch on GitHub</a></p>';
    if (historyBox) historyBox.parentElement.hidden = true;
  }

  function renderLatest(release) {
    var assets = (release.assets || []).filter(function (a) {
      return /\.(zip|exe|msi)$/i.test(a.name);
    });

    var html =
      '<div class="release-head">' +
        '<h2>' + escapeHtml(release.name || release.tag_name) + '</h2>' +
        '<span class="tag">Latest</span>' +
        '<span class="muted">Released ' + formatDate(release.published_at) + '</span>' +
      '</div>';

    if (assets.length) {
      html += '<ul class="asset-list">';
      assets.forEach(function (asset) {
        html +=
          '<li><span>' + escapeHtml(asset.name) + '</span>' +
          '<span><span class="meta">' + formatSize(asset.size) + '</span> ' +
          '<a class="btn btn-sm" href="' + asset.browser_download_url + '">Download</a></span></li>';
      });
      html += '</ul>';
    } else {
      html +=
        '<p class="muted">This release has no downloadable Windows build attached. ' +
        '<a href="' + release.html_url + '" rel="noopener">View it on GitHub</a>.</p>';
    }

    html += '<p style="margin-bottom:0"><a href="' + release.html_url + '" rel="noopener">Release notes and changelog &rarr;</a></p>';
    latestBox.innerHTML = html;
  }

  function renderHistory(releases) {
    if (!historyBox) return;
    if (releases.length < 2) {
      historyBox.parentElement.hidden = true;
      return;
    }
    historyBox.parentElement.hidden = false;
    var html = '<ul class="post-list">';
    releases.slice(1, 6).forEach(function (release) {
      html +=
        '<li><p class="post-meta"><time>' + formatDate(release.published_at) + '</time></p>' +
        '<h2><a href="' + release.html_url + '" rel="noopener">' +
        escapeHtml(release.name || release.tag_name) + '</a></h2></li>';
    });
    historyBox.innerHTML = html + '</ul>';
  }

  fetch(api)
    .then(function (response) {
      if (!response.ok) throw new Error('GitHub API returned ' + response.status);
      return response.json();
    })
    .then(function (releases) {
      var published = releases.filter(function (r) { return !r.draft; });
      if (!published.length) {
        renderNoRelease();
        return;
      }
      renderLatest(published[0]);
      renderHistory(published);
    })
    .catch(function () {
      latestBox.innerHTML =
        '<p class="muted">Could not reach the GitHub API. ' +
        '<a href="https://github.com/' + repo + '/releases/latest" rel="noopener">Open the releases page directly</a>.</p>';
      if (historyBox) historyBox.parentElement.hidden = true;
    });
})();
