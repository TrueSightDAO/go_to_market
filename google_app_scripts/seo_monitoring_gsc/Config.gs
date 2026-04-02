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
