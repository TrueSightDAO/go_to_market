/**
 * File: market_research/google_app_scripts/seo_monitoring_gsc/WeeklyGscSnapshot.gs
 * Repo: market_research (Agroverse SEO monitoring)
 *
 * Weekly Search Console snapshot → Weekly_GSC tab.
 * Uses Webmasters v3 REST (searchAnalytics/query) via UrlFetch so clasp/API push
 * accept the manifest (enabledAdvancedServices for searchConsole often fails on updateContent).
 * Authorizing user must have access to the GSC property in Config.gs.
 */

/**
 * POST searchAnalytics/query — response shape matches advanced service { rows: [...] }.
 */
function seoGscSearchAnalyticsQuery_(siteUrl, requestBody) {
  var url =
    'https://www.googleapis.com/webmasters/v3/sites/' +
    encodeURIComponent(siteUrl) +
    '/searchAnalytics/query';
  var resp = UrlFetchApp.fetch(url, {
    method: 'post',
    contentType: 'application/json',
    headers: { Authorization: 'Bearer ' + ScriptApp.getOAuthToken() },
    payload: JSON.stringify(requestBody),
    muteHttpExceptions: true,
  });
  var code = resp.getResponseCode();
  var text = resp.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error('GSC searchAnalytics/query failed: HTTP ' + code + ' ' + text);
  }
  return JSON.parse(text);
}

function seoFormatYmd_(d) {
  return (
    d.getFullYear() +
    '-' +
    ('' + (d.getMonth() + 1)).padStart(2, '0') +
    '-' +
    ('' + d.getDate()).padStart(2, '0')
  );
}

/**
 * Last complete Mon–Sun week, ending at least GSC_LAG_DAYS before today.
 */
function seoWeekRange_(today) {
  var GSC_LAG_DAYS = 3;
  var lagEnd = new Date(today.getTime());
  lagEnd.setDate(lagEnd.getDate() - GSC_LAG_DAYS);
  // Move to Sunday of that week
  var end = new Date(lagEnd.getTime());
  var dow = end.getDay();
  if (dow !== 0) {
    end.setDate(end.getDate() - dow);
  }
  end.setHours(0, 0, 0, 0);
  var start = new Date(end.getTime());
  start.setDate(start.getDate() - 6);
  return { start: start, end: end, weekStartStr: seoFormatYmd_(start), weekEndStr: seoFormatYmd_(end) };
}

function seoLoadTargetQueryMap_() {
  var cfg = SEO_MONITORING_CONFIG;
  var ss = seoGetSpreadsheet_();
  var sh = ss.getSheetByName(cfg.SH_KEYWORDS);
  var map = {};
  if (!sh) return map;
  var last = sh.getLastRow();
  if (last < 2) return map;
  var vals = sh.getRange(2, 1, last, 1).getDisplayValues();
  for (var i = 0; i < vals.length; i++) {
    var q = ('' + vals[i][0]).trim().toLowerCase();
    if (q) map[q] = true;
  }
  return map;
}

function seoDeleteRowsForWeek_(sheet, weekStartStr) {
  var last = sheet.getLastRow();
  for (var r = last; r >= 2; r--) {
    var cell = sheet.getRange(r, 1).getDisplayValue();
    if ('' + cell === weekStartStr) {
      sheet.deleteRow(r);
    }
  }
}

/**
 * Main weekly job: query GSC for query+page, append rows for the reporting week.
 * If Keywords_targets col A has values, only those queries are kept (case-insensitive).
 */
function weeklyGscSnapshot() {
  var cfg = SEO_MONITORING_CONFIG;
  var ss = seoGetSpreadsheet_();
  var out = ss.getSheetByName(cfg.SH_WEEKLY);
  if (!out) {
    throw new Error('Missing sheet tab: ' + cfg.SH_WEEKLY);
  }

  var wr = seoWeekRange_(new Date());
  var weekStartStr = wr.weekStartStr;
  var weekEndStr = wr.weekEndStr;

  seoDeleteRowsForWeek_(out, weekStartStr);

  var targetMap = seoLoadTargetQueryMap_();
  var filterOn = Object.keys(targetMap).length > 0;

  var request = {
    startDate: weekStartStr,
    endDate: weekEndStr,
    dimensions: ['query', 'page'],
    rowLimit: 25000,
  };

  var response = seoGscSearchAnalyticsQuery_(cfg.GSC_SITE_URL, request);
  var rows = response.rows || [];
  var toWrite = [];

  for (var i = 0; i < rows.length; i++) {
    var row = rows[i];
    var keys = row.keys || [];
    var q = keys[0] || '';
    var page = keys[1] || '';
    if (filterOn) {
      var ql = ('' + q).trim().toLowerCase();
      if (!targetMap[ql]) continue;
    }
    toWrite.push([
      weekStartStr,
      weekEndStr,
      q,
      page,
      row.clicks || 0,
      row.impressions || 0,
      row.ctr != null ? row.ctr : '',
      row.position != null ? row.position : '',
    ]);
    if (!filterOn && toWrite.length >= cfg.MAX_ROWS_UNFILTERED) break;
  }

  if (toWrite.length === 0) {
    toWrite.push([weekStartStr, weekEndStr, '(no matching rows)', '', 0, 0, '', '']);
  }

  var startRow = out.getLastRow() + 1;
  var n = toWrite.length;
  // getRange(row, column, numRows, numColumns) — not (lastRow, lastColumn).
  out.getRange(startRow, 1, n, 8).setValues(toWrite);
}
