/**
 * File: market_research/google_app_scripts/seo_monitoring_gsc/MonthlyDataForSeoDiscovery.gs
 *
 * Monthly DataForSEO (Google Ads keyword ideas) — ideas **not** already on Keywords_targets.
 * Credentials: Script properties DATAFORSEO_LOGIN + DATAFORSEO_PASSWORD (never in source).
 * API: https://docs.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live/
 */

var DFS_KEYWORDS_FOR_KEYWORDS_URL =
  'https://api.dataforseo.com/v3/keywords_data/google_ads/keywords_for_keywords/live';

var DFS_MONTHLY_HEADERS = [
  'pull_date',
  'keyword',
  'search_volume',
  'competition',
  'competition_index',
  'cpc',
  'low_top_of_page_bid',
  'high_top_of_page_bid',
  'note',
];

function dfsGetScriptCreds_() {
  var props = PropertiesService.getScriptProperties();
  var login = (props.getProperty('DATAFORSEO_LOGIN') || '').trim();
  var password = (props.getProperty('DATAFORSEO_PASSWORD') || '').trim();
  if (!login || !password) {
    throw new Error(
      'Missing DataForSEO credentials. Project Settings → Script properties: set DATAFORSEO_LOGIN and DATAFORSEO_PASSWORD. See folder README.'
    );
  }
  return { login: login, password: password };
}

/**
 * Optional override: comma-separated seeds (max 20 used per API call).
 */
function dfsGetSeeds_(props) {
  var raw = (props.getProperty('DATAFORSEO_SEEDS') || '').trim();
  if (raw) {
    var parts = raw.split(',');
    var out = [];
    for (var i = 0; i < parts.length; i++) {
      var s = ('' + parts[i]).trim();
      if (s) out.push(s);
    }
    return out.slice(0, 20);
  }
  var d = SEO_MONITORING_CONFIG.DATAFORSEO_DEFAULT_SEEDS || [];
  return d.slice(0, 20);
}

function dfsLoadActiveKeywordSet_() {
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

function dfsEnsureMonthlySheet_(ss, title) {
  var sh = ss.getSheetByName(title);
  if (!sh) {
    sh = ss.insertSheet(title);
  }
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, DFS_MONTHLY_HEADERS.length).setValues([DFS_MONTHLY_HEADERS]);
    sh.setFrozenRows(1);
    return sh;
  }
  var head = sh.getRange(1, 1, 1, DFS_MONTHLY_HEADERS.length).getValues()[0];
  for (var c = 0; c < DFS_MONTHLY_HEADERS.length; c++) {
    if (String(head[c] || '') !== DFS_MONTHLY_HEADERS[c]) {
      throw new Error('Expected header in row 1 of ' + title + '; fix or recreate tab.');
    }
  }
  return sh;
}

function dfsRowsFromApiResponse_(data) {
  var out = [];
  var tasks = data.tasks || [];
  for (var t = 0; t < tasks.length; t++) {
    var task = tasks[t];
    var results = task.result || [];
    for (var r = 0; r < results.length; r++) {
      var b = results[r];
      if (!b || typeof b !== 'object') continue;
      out.push({
        keyword: b.keyword || '',
        search_volume: b.search_volume,
        competition: b.competition,
        competition_index: b.competition_index,
        cpc: b.cpc,
        low_top_of_page_bid: b.low_top_of_page_bid,
        high_top_of_page_bid: b.high_top_of_page_bid,
      });
    }
  }
  return out;
}

function dfsDedupeSort_(rows) {
  var byKw = {};
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    var k = ('' + r.keyword).trim().toLowerCase();
    if (!k) continue;
    var prev = byKw[k];
    if (!prev) {
      byKw[k] = r;
      continue;
    }
    var pv = prev.search_volume;
    var cv = r.search_volume;
    if (cv != null && (pv == null || cv > pv)) byKw[k] = r;
  }
  var list = [];
  for (var key in byKw) {
    if (Object.prototype.hasOwnProperty.call(byKw, key)) list.push(byKw[key]);
  }
  list.sort(function (a, b) {
    var av = a.search_volume;
    var bv = b.search_volume;
    var ae = av == null || av === '';
    var be = bv == null || bv === '';
    if (ae && be) return 0;
    if (ae) return 1;
    if (be) return -1;
    return Number(bv) - Number(av);
  });
  return list;
}

function dfsFetchKeywordsForKeywords_(login, password, seeds, taskBody) {
  var body = [{}];
  body[0].keywords = seeds;
  body[0].language_code = taskBody.language_code;
  body[0].sort_by = taskBody.sort_by;
  if (taskBody.location_name) body[0].location_name = taskBody.location_name;
  else body[0].location_code = taskBody.location_code;

  var token = Utilities.base64Encode(login + ':' + password);
  var resp = UrlFetchApp.fetch(DFS_KEYWORDS_FOR_KEYWORDS_URL, {
    method: 'post',
    contentType: 'application/json',
    headers: {
      Authorization: 'Basic ' + token,
    },
    payload: JSON.stringify(body),
    muteHttpExceptions: true,
  });
  var code = resp.getResponseCode();
  var text = resp.getContentText();
  if (code < 200 || code >= 300) {
    throw new Error('DataForSEO HTTP ' + code + ' ' + text);
  }
  return JSON.parse(text);
}

/**
 * Run monthly (or on demand). Appends rows to DataForSEO_monthly_discovery for keywords
 * returned by DataForSEO that are **not** listed in Keywords_targets column A.
 */
function monthlyDataForSeoKeywordDiscovery() {
  var cfg = SEO_MONITORING_CONFIG;
  var creds = dfsGetScriptCreds_();
  var props = PropertiesService.getScriptProperties();
  var seeds = dfsGetSeeds_(props);
  if (!seeds.length) {
    throw new Error('No keyword seeds; set DATAFORSEO_SEEDS or DATAFORSEO_DEFAULT_SEEDS in Config.gs');
  }

  var taskBody = {
    language_code: cfg.DATAFORSEO_LANGUAGE_CODE || 'en',
    sort_by: cfg.DATAFORSEO_SORT_BY || 'search_volume',
    location_code: cfg.DATAFORSEO_LOCATION_CODE || 2840,
    location_name: (cfg.DATAFORSEO_LOCATION_NAME || '').trim(),
  };

  var data = dfsFetchKeywordsForKeywords_(creds.login, creds.password, seeds, taskBody);
  var st = data.status_code;
  if (st !== 20000) {
    throw new Error(
      'DataForSEO API status_code=' + st + ' message=' + (data.status_message || '')
    );
  }

  var rawRows = dfsDedupeSort_(dfsRowsFromApiResponse_(data));
  var active = dfsLoadActiveKeywordSet_();
  var pullDate = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  var cap = cfg.DATAFORSEO_MAX_ROWS_PER_RUN || 500;
  var toWrite = [];

  for (var i = 0; i < rawRows.length && toWrite.length < cap; i++) {
    var row = rawRows[i];
    var kw = ('' + row.keyword).trim();
    var kl = kw.toLowerCase();
    if (!kl) continue;
    if (active[kl]) continue;
    toWrite.push([
      pullDate,
      kw,
      row.search_volume != null ? row.search_volume : '',
      row.competition != null ? row.competition : '',
      row.competition_index != null ? row.competition_index : '',
      row.cpc != null ? row.cpc : '',
      row.low_top_of_page_bid != null ? row.low_top_of_page_bid : '',
      row.high_top_of_page_bid != null ? row.high_top_of_page_bid : '',
      'not in Keywords_targets',
    ]);
  }

  var ss = seoGetSpreadsheet_();
  var out = dfsEnsureMonthlySheet_(ss, cfg.SH_MONTHLY_DFS);
  if (toWrite.length === 0) {
    var emptyStart = out.getLastRow() + 1;
    out.getRange(emptyStart, 1, 1, DFS_MONTHLY_HEADERS.length).setValues([
      [
        pullDate,
        '(no new opportunities vs Keywords_targets)',
        '',
        '',
        '',
        '',
        '',
        '',
        'all ideas were already on Keywords_targets or API returned empty',
      ],
    ]);
    return;
  }
  var startRow = out.getLastRow() + 1;
  var n = toWrite.length;
  out.getRange(startRow, 1, n, DFS_MONTHLY_HEADERS.length).setValues(toWrite);
}
