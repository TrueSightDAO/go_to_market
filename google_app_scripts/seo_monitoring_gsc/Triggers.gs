/**
 * File: market_research/google_app_scripts/seo_monitoring_gsc/Triggers.gs
 * Repo: market_research
 *
 * Run installWeeklyTrigger() once after authorizing the script.
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
