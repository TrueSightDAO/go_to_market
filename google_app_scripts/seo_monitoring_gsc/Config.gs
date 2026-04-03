/**
 * File: market_research/google_app_scripts/seo_monitoring_gsc/Config.gs
 * Repo: market_research
 *
 * Spreadsheet-bound SEO monitoring — tab names and GSC property URL.
 * Adjust GSC_SITE_URL to match Google Search Console exactly.
 */
var SEO_MONITORING_CONFIG = {
  /**
   * Workbook id when the script is standalone (script.google.com). Container-bound projects
   * can leave this set; getActiveSpreadsheet() is used first when non-null.
   */
  SPREADSHEET_ID: '1qRlufSUQusQbJc3AwonIvHtfiAQjwhnMtl79FFkGBt8',

  /** Exact property URL from Google Search Console (e.g. sc-domain:agroverse.shop) */
  GSC_SITE_URL: 'sc-domain:agroverse.shop',

  /** Cap rows appended per run when Keywords_targets is empty (all queries). */
  MAX_ROWS_UNFILTERED: 2000,

  /** Tab names — must match bootstrap_seo_monitoring_sheet.py */
  SH_INSTRUCTIONS: 'Instructions',
  SH_KEYWORDS: 'Keywords_targets',
  SH_CHANGELOG: 'Change_log',
  SH_WEEKLY: 'Weekly_GSC',
  /** Monthly DataForSEO keyword ideas not already on Keywords_targets (col A). */
  SH_MONTHLY_DFS: 'DataForSEO_monthly_discovery',

  /**
   * DataForSEO keywords_for_keywords/live — seeds (max 20 sent per API call).
   * Override via Script property DATAFORSEO_SEEDS (comma-separated).
   */
  DATAFORSEO_DEFAULT_SEEDS: [
    'ceremonial cacao',
    'buy ceremonial cacao',
    'organic cacao nibs',
    'cacao nibs organic',
    'ceremonial grade cacao',
    'bulk cacao nibs',
    'brazilian cacao',
    'single origin cacao',
    'amazon rainforest cacao',
    'fair trade cacao',
    'wholesale cacao',
    'cacao paste ceremonial',
    'regenerative cacao',
  ],

  /** United States — use location_name instead to override (e.g. "United States"). */
  DATAFORSEO_LOCATION_CODE: 2840,
  DATAFORSEO_LOCATION_NAME: '',
  DATAFORSEO_LANGUAGE_CODE: 'en',
  DATAFORSEO_SORT_BY: 'search_volume',
  /** Max opportunity rows appended per monthly run (after filters). */
  DATAFORSEO_MAX_ROWS_PER_RUN: 500,
};

/**
 * Standalone script projects have no "active" spreadsheet; open by id from config.
 */
function seoGetSpreadsheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (ss) return ss;
  var id = SEO_MONITORING_CONFIG.SPREADSHEET_ID;
  if (!id || String(id).trim() === '') {
    throw new Error(
      'No active spreadsheet. Open this script from the workbook (Extensions → Apps Script) ' +
        'or set SEO_MONITORING_CONFIG.SPREADSHEET_ID in Config.gs.'
    );
  }
  return SpreadsheetApp.openById(String(id).trim());
}
