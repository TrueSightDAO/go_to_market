/**
 * File: market_research/google_app_scripts/seo_monitoring_gsc/Triggers.gs
 * Repo: market_research
 *
 * Run installWeeklyTrigger() / installMonthlyDataForSeoTrigger() once after authorizing.
 */
function installWeeklyTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'weeklyGscSnapshot') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('weeklyGscSnapshot')
    .timeBased()
    .everyWeeks(1)
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(8)
    .create();
}

/** Manual test without waiting for Monday. */
function runWeeklyGscSnapshotNow() {
  weeklyGscSnapshot();
}

/** Monthly DataForSEO keyword ideas (1st of month, 09:00 in script timezone). */
function installMonthlyDataForSeoTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'monthlyDataForSeoKeywordDiscovery') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('monthlyDataForSeoKeywordDiscovery')
    .timeBased()
    .onMonthDay(1)
    .atHour(9)
    .create();
}

/** Manual test for DataForSEO monthly job. */
function runMonthlyDataForSeoDiscoveryNow() {
  monthlyDataForSeoKeywordDiscovery();
}
