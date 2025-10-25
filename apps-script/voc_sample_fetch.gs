/**
 * Returns up to `limit` rows from the 공지문의 시트 for a quick sanity check.
 * Only _id, created_at, and content columns are included so we can validate
 * that column references are correct before wiring the full pipeline.
 */
function fetchSampleRows(limit) {
  var sheetId = '19z32Cbsfaf8zdDX_eXQAEPlBuNrCxK4AnyQX07dib0M';
  var sheetName = '공지문의';
  var maxRows = limit || 3;

  var spreadsheet = SpreadsheetApp.openById(sheetId);
  var sheet = spreadsheet.getSheetByName(sheetName);

  if (!sheet) {
    throw new Error('Sheet "' + sheetName + '" not found.');
  }

  // Header row is assumed to start at row 1.
  var header = sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0];
  var idCol = header.indexOf('_id') + 1;
  var createdAtCol = header.indexOf('created_at') + 1;
  var contentCol = header.indexOf('content') + 1;

  if (idCol === 0 || createdAtCol === 0 || contentCol === 0) {
    throw new Error('One of the required columns (_id, created_at, content) is missing.');
  }

  var lastRow = sheet.getLastRow();
  if (lastRow < 2) {
    return [];
  }

  var rowCount = Math.min(maxRows, lastRow - 1);
  var idValues = sheet.getRange(2, idCol, rowCount, 1).getValues();
  var createdValues = sheet.getRange(2, createdAtCol, rowCount, 1).getValues();
  var contentValues = sheet.getRange(2, contentCol, rowCount, 1).getValues();

  var result = [];
  for (var i = 0; i < rowCount; i++) {
    result.push({
      _id: idValues[i][0],
      created_at: createdValues[i][0],
      content: contentValues[i][0]
    });
  }

  Logger.log(JSON.stringify(result, null, 2));
  return result;
}

/**
 * Convenience wrapper for the Apps Script editor to log 3 sample rows.
 */
function debugFetchSampleRows() {
  return fetchSampleRows(3);
}
