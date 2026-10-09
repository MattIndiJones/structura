// Use the user's calendar date, including just after midnight and leap years.
export function previousLocalYearDate(today = new Date()) {
  const year = today.getFullYear() - 1
  const month = today.getMonth()
  const day = Math.min(today.getDate(), new Date(year, month + 1, 0).getDate())
  return `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`
}
