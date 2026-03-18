/**
 * Google Apps Script — Paper Pipeline Email Parser
 *
 * This script runs inside your Google account (Extensions → Apps Script).
 * It scans Google Scholar and SSRN alert emails, extracts paper info,
 * and writes it to a Google Sheet that your pipeline fetches.
 *
 * SETUP:
 * 1. Create a new Google Sheet called "Paper Pipeline Inbox"
 * 2. Open Extensions → Apps Script
 * 3. Paste this entire script, replacing the default code
 * 4. Update SHEET_NAME below if you used a different name
 * 5. Click Run → select "processAlerts" → Authorize when prompted
 * 6. Set up a trigger: Triggers (clock icon) → Add Trigger →
 *    Function: processAlerts, Event: Time-driven, Day timer, 6am-7am
 * 7. Publish the sheet: File → Share → Publish to web →
 *    Select "Sheet1" → CSV format → Publish → Copy the URL
 * 8. Paste that URL as GSHEET_CSV_URL in your .env file
 */

const SHEET_NAME = "Paper Pipeline Inbox";
const DAYS_TO_SCAN = 7; // How many days back to scan emails

function processAlerts() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Sheet1");
  if (!sheet) {
    throw new Error("Sheet1 not found. Make sure your sheet has a tab called Sheet1.");
  }

  // Set up headers if empty
  if (sheet.getLastRow() === 0) {
    sheet.appendRow(["title", "doi", "url", "authors", "source", "date_found"]);
  }

  // Get existing DOIs/URLs to avoid duplicates
  const existingData = sheet.getDataRange().getValues();
  const existingUrls = new Set();
  for (let i = 1; i < existingData.length; i++) {
    if (existingData[i][1]) existingUrls.add(existingData[i][1]); // DOI column
    if (existingData[i][2]) existingUrls.add(existingData[i][2]); // URL column
  }

  const cutoffDate = new Date();
  cutoffDate.setDate(cutoffDate.getDate() - DAYS_TO_SCAN);

  // Process Google Scholar alerts
  const scholarPapers = processScholarAlerts(cutoffDate, existingUrls);

  // Process SSRN alerts
  const ssrnPapers = processSSRNAlerts(cutoffDate, existingUrls);

  // Write new papers to sheet
  const allPapers = scholarPapers.concat(ssrnPapers);
  for (const paper of allPapers) {
    sheet.appendRow([
      paper.title,
      paper.doi,
      paper.url,
      paper.authors,
      paper.source,
      new Date().toISOString()
    ]);
  }

  Logger.log(`Added ${allPapers.length} new papers (${scholarPapers.length} Scholar, ${ssrnPapers.length} SSRN)`);
}

function processScholarAlerts(cutoffDate, existingUrls) {
  const papers = [];
  const threads = GmailApp.search(
    'from:scholaralerts-noreply@google.com after:' + formatDate(cutoffDate),
    0, 50
  );

  for (const thread of threads) {
    for (const message of thread.getMessages()) {
      const body = message.getBody();
      const extracted = extractScholarPapers(body);
      for (const paper of extracted) {
        if (!existingUrls.has(paper.doi) && !existingUrls.has(paper.url)) {
          papers.push(paper);
          existingUrls.add(paper.url);
          if (paper.doi) existingUrls.add(paper.doi);
        }
      }
    }
  }
  return papers;
}

function processSSRNAlerts(cutoffDate, existingUrls) {
  const papers = [];
  const threads = GmailApp.search(
    'from:SSRN@email.ssrn.com after:' + formatDate(cutoffDate),
    0, 50
  );

  // Also try the other common SSRN sender
  const threads2 = GmailApp.search(
    'from:noreply@ssrn.com after:' + formatDate(cutoffDate),
    0, 50
  );

  const allThreads = threads.concat(threads2);

  for (const thread of allThreads) {
    for (const message of thread.getMessages()) {
      const body = message.getBody();
      const extracted = extractSSRNPapers(body);
      for (const paper of extracted) {
        if (!existingUrls.has(paper.doi) && !existingUrls.has(paper.url)) {
          papers.push(paper);
          existingUrls.add(paper.url);
          if (paper.doi) existingUrls.add(paper.doi);
        }
      }
    }
  }
  return papers;
}

function extractScholarPapers(html) {
  const papers = [];

  // Google Scholar alert emails contain links in <h3> tags or <a> tags with class "gse_alrt_title"
  // Pattern: <a href="URL" class="gse_alrt_title">TITLE</a>
  const titlePattern = /<a[^>]*href="([^"]*)"[^>]*class="gse_alrt_title"[^>]*>(.*?)<\/a>/gi;
  let match;

  while ((match = titlePattern.exec(html)) !== null) {
    let url = match[1];
    let title = match[2].replace(/<[^>]+>/g, '').trim(); // Strip inner HTML tags

    // Google Scholar wraps URLs through their redirect
    if (url.includes('scholar_url?url=')) {
      const realUrl = url.match(/scholar_url\?url=([^&]+)/);
      if (realUrl) url = decodeURIComponent(realUrl[1]);
    }

    // Try to extract DOI from URL
    let doi = '';
    const doiMatch = url.match(/doi\.org\/(.+?)(?:\?|$|#)/);
    if (doiMatch) doi = decodeURIComponent(doiMatch[1]);

    if (title) {
      papers.push({
        title: title,
        doi: doi,
        url: url,
        authors: '', // Scholar alerts don't reliably include authors in a parseable way
        source: 'google_scholar'
      });
    }
  }

  // Fallback: try simpler pattern if the class-based one didn't match
  if (papers.length === 0) {
    const simplePattern = /<h3[^>]*><a[^>]*href="([^"]*)"[^>]*>(.*?)<\/a><\/h3>/gi;
    while ((match = simplePattern.exec(html)) !== null) {
      let url = match[1];
      let title = match[2].replace(/<[^>]+>/g, '').trim();

      if (url.includes('scholar_url?url=')) {
        const realUrl = url.match(/scholar_url\?url=([^&]+)/);
        if (realUrl) url = decodeURIComponent(realUrl[1]);
      }

      let doi = '';
      const doiMatch = url.match(/doi\.org\/(.+?)(?:\?|$|#)/);
      if (doiMatch) doi = decodeURIComponent(doiMatch[1]);

      if (title) {
        papers.push({
          title: title,
          doi: doi,
          url: url,
          authors: '',
          source: 'google_scholar'
        });
      }
    }
  }

  return papers;
}

function extractSSRNPapers(html) {
  const papers = [];

  // SSRN emails typically contain links to papers.ssrn.com/sol3/papers.cfm?abstract_id=XXXXXXX
  // or ssrn.com/abstract=XXXXXXX
  const ssrnPattern = /<a[^>]*href="(https?:\/\/[^"]*ssrn\.com[^"]*(?:abstract_id|abstract=)\d+[^"]*)"[^>]*>(.*?)<\/a>/gi;
  let match;

  while ((match = ssrnPattern.exec(html)) !== null) {
    let url = match[1];
    let title = match[2].replace(/<[^>]+>/g, '').trim();

    // Skip if title is too short (probably a "View" or "Download" link)
    if (title.length < 10) continue;
    // Skip navigation links
    if (title.toLowerCase().includes('click here') || title.toLowerCase().includes('view paper')) continue;

    if (title) {
      papers.push({
        title: title,
        doi: '', // SSRN papers often don't have DOIs yet
        url: url,
        authors: '',
        source: 'ssrn'
      });
    }
  }

  return papers;
}

function formatDate(date) {
  return date.getFullYear() + '/' +
    String(date.getMonth() + 1).padStart(2, '0') + '/' +
    String(date.getDate()).padStart(2, '0');
}

/**
 * Optional: Clean up old entries (run monthly)
 * Removes rows older than 60 days to keep the sheet manageable.
 */
function cleanupOldEntries() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Sheet1");
  const data = sheet.getDataRange().getValues();
  const cutoff = new Date();
  cutoff.setDate(cutoff.getDate() - 60);

  // Work backwards to avoid index shifting
  for (let i = data.length - 1; i >= 1; i--) {
    const dateFound = new Date(data[i][5]);
    if (dateFound < cutoff) {
      sheet.deleteRow(i + 1);
    }
  }
}
