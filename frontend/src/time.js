// The API sends times in UTC, e.g. "2026-10-08T05:27:03Z". The restaurant is in Aurora, IL, so staff
// should see Chicago time no matter where the browser is. The browser's built-in time zone data
// handles daylight saving time, which is why the server no longer needs the tzdata package

const chicagoTime = new Intl.DateTimeFormat('en-US', {
  timeZone: 'America/Chicago',
  month: 'short',
  day: '2-digit',
  hour: 'numeric',
  minute: '2-digit',
})

export function formatOrderTime(isoTime) {
  // e.g. "Oct 08, 12:27 AM"
  return chicagoTime.format(new Date(isoTime))
}
