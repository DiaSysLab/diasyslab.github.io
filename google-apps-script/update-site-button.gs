/**
 * Adds an "🚀 Update Site" menu to the spreadsheet with a button that
 * triggers the site's GitHub Actions build/deploy immediately, instead of
 * waiting for a scheduled run (there isn't one — see readme.md).
 *
 * Setup: paste this whole file into the spreadsheet's Apps Script project,
 * then follow "Updating the site instantly from Google Sheets" in readme.md
 * to create the GitHub token and Script Properties this needs.
 */

function onOpen() {
  SpreadsheetApp.getUi()
    .createMenu('🚀 Update Site')
    .addItem('Update site now', 'triggerSiteUpdate')
    .addToUi();
}

function triggerSiteUpdate() {
  var ui = SpreadsheetApp.getUi();
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('GITHUB_TOKEN');
  var owner = props.getProperty('GITHUB_OWNER');
  var repo = props.getProperty('GITHUB_REPO');
  var branch = props.getProperty('GITHUB_BRANCH') || 'master';

  if (!token || !owner || !repo) {
    ui.alert(
      'Missing setup: add GITHUB_TOKEN, GITHUB_OWNER, and GITHUB_REPO in ' +
      'this Apps Script project\'s Settings -> Script Properties. See ' +
      '"Updating the site instantly from Google Sheets" in readme.md.'
    );
    return;
  }

  var url = 'https://api.github.com/repos/' + owner + '/' + repo +
    '/actions/workflows/builder.yml/dispatches';

  var response = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Bearer ' + token,
      Accept: 'application/vnd.github+json',
    },
    payload: JSON.stringify({ ref: branch }),
    muteHttpExceptions: true,
  });

  var code = response.getResponseCode();
  if (code === 204) {
    ui.alert('✅ Site update triggered! It usually takes a couple of minutes — check the repo\'s Actions tab for progress.');
  } else {
    ui.alert('❌ Failed (HTTP ' + code + '): ' + response.getContentText());
  }
}
