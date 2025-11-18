/**
 * File: google_apps_scripts/market_research/find_nearby_stores.gs
 * Repository: https://github.com/TrueSightDAO/market_research
 * 
 * Description: REST API endpoint for finding nearby stores from the holistic wellness hit list.
 * Provides distance-based queries to find the top N stores nearest to a given location.
 * Filters stores by status (default: "Contacted") and returns results ordered by distance.
 * Supports status updates with digital signature tracking for audit trails.
 */

/**
 * Web app to find nearby stores from the holistic wellness hit list spreadsheet.
 * 
 * Deployment URL: https://script.google.com/macros/s/AKfycbwB2zqNV9nMCMWs2hSa8FecjA36Oh-mSVuz3pk8TpXrXcy9dvqOqgbWIirNka2LmacgPw/exec
 * 
 * Query parameters (for search):
 *   lat=<number>          : User's latitude (required)
 *   lng=<number>          : User's longitude (required)
 *   limit=<number>        : Maximum number of results (optional, default: 10, max: 50 without bounds, max: 200 with bounds)
 *   status=<string>       : Filter by store status (optional, default: "Contacted")
 *                           Valid values: "Contacted", "Research", "Partnered", "Rejected", or any status value
 *                           Use empty string "" or omit parameter to show all statuses
 *   ne_lat=<number>       : Northeast latitude bound (optional, for map viewport filtering)
 *   ne_lng=<number>       : Northeast longitude bound (optional, for map viewport filtering)
 *   sw_lat=<number>       : Southwest latitude bound (optional, for map viewport filtering)
 *   sw_lng=<number>       : Southwest longitude bound (optional, for map viewport filtering)
 *                           When all four bounds parameters are provided, only stores within the bounds are returned
 *   shop_type=<string>    : Filter by shop type (optional)
 *                           Valid values: "Metaphysical/Spiritual", "Wellness Center", "Health Food Store", etc.
 *                           Use empty string "" or omit parameter to show all shop types
 * 
 * Query parameters (for status update):
 *   action=update_status     : Action to update store status
 *   shop_name=<string>       : Name of the shop to update (required)
 *   new_status=<string>      : New status value (required)
 *                              Valid values: "Contacted", "Research", "Partnered", "Rejected", or any status value
 *   shop_type=<string>       : New shop type value (optional)
 *                              Valid values: "Metaphysical/Spiritual", "Wellness Center", "Health Food Store", etc.
 *   digital_signature=<string> : Digital signature (public key) of the person making the change (optional but recommended for audit trail)
 * 
 * Response format:
 *   {
 *     "success": true,
 *     "location": { "latitude": <number>, "longitude": <number> },
 *     "status_filter": "<string>",
 *     "count": <number>,
 *     "stores": [
 *       {
 *         "name": "<string>",
 *         "address": "<string>",
 *         "city": "<string>",
 *         "state": "<string>",
 *         "phone": "<string>",
 *         "website": "<string>",
 *         "email": "<string>",
 *         "instagram": "<string>",
 *         "shop_type": "<string>",
 *         "priority": "<string>",
 *         "status": "<string>",
 *         "notes": "<string>",
 *         "contact_date": "<string>",
 *         "contact_method": "<string>",
 *         "latitude": <number>,
 *         "longitude": <number>",
 *         "distance": <number>  // Distance in miles
 *       },
 *       ...
 *     ]
 *   }
 * 
 * Error response:
 *   {
 *     "success": false,
 *     "error": "<error message>"
 *   }
 * 
 * Instructions to call this endpoint:
 * 1. Deploy this script as a web app:
 *    - Click Deploy > New deployment > Web app.
 *    - Set "Execute as" to "Me" and "Who has access" to "Anyone" (or restrict as needed).
 *    - Click Deploy and copy the web app URL.
 * 2. Make an HTTP GET request with latitude and longitude:
 *    - URL format: <web_app_url>?lat=37.7749&lng=-122.4194&limit=10&status=Contacted
 *    - Example: https://script.google.com/macros/s/<ID>/exec?lat=37.7749&lng=-122.4194&limit=10
 * 3. Use a tool like curl, Postman, or JavaScript fetch to test:
 *    - curl: curl "<web_app_url>?lat=37.7749&lng=-122.4194&limit=10"
 *    - JavaScript: fetch("<web_app_url>?lat=37.7749&lng=-122.4194&limit=10").then(res => res.json())
 * 4. To test the function directly:
 *    - Open the script editor and run the testFindNearbyStores() function.
 *    - Check the Logs (View > Logs) for the result.
 * 
 * Note: Ensure the spreadsheet ID and sheet name defined in constants below match your setup.
 */

// Constants for spreadsheet ID and sheet name
const SPREADSHEET_ID = '1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc';
const SHEET_NAME = 'Hit List';
const DAPP_REMARKS_SHEET = 'DApp Remarks';

/**
 * Calculate distance between two points using Haversine formula
 * Returns distance in miles
 * @param {number} lat1 - Latitude of first point
 * @param {number} lon1 - Longitude of first point
 * @param {number} lat2 - Latitude of second point
 * @param {number} lon2 - Longitude of second point
 * @return {number} Distance in miles
 */
function calculateDistance(lat1, lon1, lat2, lon2) {
  const R = 3959; // Earth's radius in miles
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  const distance = R * c;
  
  return distance;
}

/**
 * Convert degrees to radians
 * @param {number} degrees - Angle in degrees
 * @return {number} Angle in radians
 */
function toRad(degrees) {
  return degrees * (Math.PI / 180);
}

/**
 * Normalize a string for use in store keys.
 * @param {string} value
 * @return {string}
 */
function normalizeForKey_(value) {
  if (!value) {
    return '';
  }
  return String(value)
    .trim()
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9\-]/g, '');
}

/**
 * Create a deterministic key for a store based on its core address fields.
 * @param {string} name
 * @param {string} address
 * @param {string} city
 * @param {string} state
 * @return {string}
 */
function createStoreKey_(name, address, city, state) {
  const parts = [
    normalizeForKey_(name),
    normalizeForKey_(address),
    normalizeForKey_(city),
    normalizeForKey_(state)
  ].filter(Boolean);
  return parts.join('__');
}

/**
 * Check if a point is within bounds
 * @param {number} lat - Latitude to check
 * @param {number} lng - Longitude to check
 * @param {number} neLat - Northeast latitude bound
 * @param {number} neLng - Northeast longitude bound
 * @param {number} swLat - Southwest latitude bound
 * @param {number} swLng - Southwest longitude bound
 * @return {boolean} True if point is within bounds
 */
function isWithinBounds(lat, lng, neLat, neLng, swLat, swLng) {
  // Handle longitude wrapping (crossing the 180/-180 meridian)
  if (neLng < swLng) {
    // Bounds cross the date line
    return lat >= swLat && lat <= neLat && (lng >= swLng || lng <= neLng);
  } else {
    // Normal case
    return lat >= swLat && lat <= neLat && lng >= swLng && lng <= neLng;
  }
}

/**
 * Find nearby stores from the spreadsheet
 * @param {number} userLat - User's latitude
 * @param {number} userLng - User's longitude
 * @param {number} limit - Maximum number of results (default: 10)
 * @param {Array<string>|null} statusFilters - Filter by store status(es) (default: ["Contacted"]). Use null or empty array to show all statuses
 * @param {Object|null} bounds - Optional bounds object with neLat, neLng, swLat, swLng to filter stores by visible area
 * @param {Array<string>|null} shopTypeFilters - Filter by shop type(s) (optional). Use null or empty array to show all shop types
 * @return {Array} Array of store objects with distance
 */
function findNearbyStores(userLat, userLng, limit, statusFilters, bounds, shopTypeFilters) {
  // Default statusFilters to ["Contacted"] if not provided (but null or empty array means show all)
  if (statusFilters === undefined || statusFilters === null) {
    statusFilters = ["Contacted"];
  }
  // If statusFilters is empty array, it means show all statuses
  if (Array.isArray(statusFilters) && statusFilters.length === 0) {
    statusFilters = null;
  }
  // Convert single value to array for consistency
  if (!Array.isArray(statusFilters) && statusFilters !== null) {
    statusFilters = [statusFilters];
  }
  
  // Handle shopTypeFilters similarly
  if (shopTypeFilters !== undefined && shopTypeFilters !== null) {
    if (Array.isArray(shopTypeFilters) && shopTypeFilters.length === 0) {
      shopTypeFilters = null;
    } else if (!Array.isArray(shopTypeFilters)) {
      shopTypeFilters = [shopTypeFilters];
    }
  }
  try {
    // Open the spreadsheet
    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME);
    
    if (!sheet) {
      throw new Error(`Sheet "${SHEET_NAME}" not found`);
    }
    
    // Get all data
    const data = sheet.getDataRange().getValues();
    if (data.length < 2) {
      return []; // No data rows
    }
    
    // Find column indices
    const headers = data[0];
    const shopNameIdx = headers.indexOf("Shop Name");
    const statusIdx = headers.indexOf("Status");
    const latIdx = headers.indexOf("Latitude");
    const lngIdx = headers.indexOf("Longitude");
    const salesNotesIdx = headers.indexOf("Sales Process Notes");
    const addressIdx = headers.indexOf("Address");
    const cityIdx = headers.indexOf("City");
    const stateIdx = headers.indexOf("State");
    const phoneIdx = headers.indexOf("Phone");
    const websiteIdx = headers.indexOf("Website");
    const emailIdx = headers.indexOf("Email");
    const instagramIdx = headers.indexOf("Instagram");
    const shopTypeIdx = headers.indexOf("Shop Type");
    
    if (shopNameIdx === -1 || statusIdx === -1 || latIdx === -1 || lngIdx === -1) {
      throw new Error("Required columns not found in sheet");
    }
    const priorityIdx = headers.indexOf("Priority");
    const notesIdx = headers.indexOf("Notes");
    const contactDateIdx = headers.indexOf("Contact Date");
    const contactMethodIdx = headers.indexOf("Contact Method");
    const followUpDateIdx = headers.indexOf("Follow Up Date");
    const contactPersonIdx = headers.indexOf("Contact Person");
    const ownerNameIdx = headers.indexOf("Owner Name");
    const referralIdx = headers.indexOf("Referral");
    const productInterestIdx = headers.indexOf("Product Interest");
    const followUpEventLinkIdx = headers.indexOf("Follow Up Event Link");
    const visitDateIdx = headers.indexOf("Visit Date");
    const outcomeIdx = headers.indexOf("Outcome");
    
    // Process rows and filter by status and shop type
    const stores = [];
    
    // Log filtering info for debugging
    Logger.log("Filtering stores with statusFilter: " + statusFilter + " (type: " + typeof statusFilter + ")");
    if (shopTypeFilter) {
      Logger.log("Filtering stores with shopTypeFilter: " + shopTypeFilter);
    }
    
    for (let i = 1; i < data.length; i++) {
      const row = data[i];
      
      // Get status from row and normalize it
      const status = row[statusIdx];
      const rowStatus = status ? String(status).trim() : "";
      
      // Apply status filter(s) (if statusFilters is null, show all stores regardless of status)
      if (statusFilters !== null && statusFilters !== undefined && statusFilters.length > 0) {
        // Check if row status matches any of the selected status filters
        const matchesStatus = statusFilters.some(filterStatus => {
          const trimmedFilter = String(filterStatus).trim();
          return rowStatus === trimmedFilter;
        });
        if (!matchesStatus) {
          continue; // Skip this store - it doesn't match any of the selected status filters
        }
      }
      // If statusFilters is null or empty, we show all stores (no filtering)
      
      // Apply shop type filter(s) if provided
      if (shopTypeFilters !== null && shopTypeFilters !== undefined && shopTypeFilters.length > 0) {
        const rowShopType = shopTypeIdx >= 0 ? (row[shopTypeIdx] ? String(row[shopTypeIdx]).trim() : "") : "";
        // Check if row shop type matches any of the selected shop type filters
        const matchesShopType = shopTypeFilters.some(filterShopType => {
          const trimmedFilter = String(filterShopType).trim();
          return rowShopType === trimmedFilter;
        });
        if (!matchesShopType) {
          continue; // Skip this store - it doesn't match any of the selected shop type filters
        }
      }
      
      // Get coordinates
      const latStr = row[latIdx];
      const lngStr = row[lngIdx];
      
      // Skip if no coordinates
      if (!latStr || !lngStr || latStr === "" || lngStr === "") {
        continue;
      }
      
      // Parse coordinates
      let storeLat, storeLng;
      try {
        storeLat = parseFloat(latStr);
        storeLng = parseFloat(lngStr);
        
        if (isNaN(storeLat) || isNaN(storeLng)) {
          continue;
        }
      } catch (e) {
        continue;
      }
      
      // Filter by bounds FIRST if provided (for map viewport filtering)
      // This is more efficient - check bounds before calculating distance
      if (bounds && bounds.neLat !== null && bounds.neLng !== null && bounds.swLat !== null && bounds.swLng !== null) {
        if (!isWithinBounds(storeLat, storeLng, bounds.neLat, bounds.neLng, bounds.swLat, bounds.swLng)) {
          continue; // Store is outside the visible bounds
        }
      }
      
      // Calculate distance
      const distance = calculateDistance(userLat, userLng, storeLat, storeLng);
      
      // Build store object with all available fields
      const store = {
        name: row[shopNameIdx] || "",
        address: addressIdx >= 0 ? (row[addressIdx] || "") : "",
        city: cityIdx >= 0 ? (row[cityIdx] || "") : "",
        state: stateIdx >= 0 ? (row[stateIdx] || "") : "",
        phone: phoneIdx >= 0 ? (row[phoneIdx] || "") : "",
        website: websiteIdx >= 0 ? (row[websiteIdx] || "") : "",
        email: emailIdx >= 0 ? (row[emailIdx] || "") : "",
        instagram: instagramIdx >= 0 ? (row[instagramIdx] || "") : "",
        shop_type: shopTypeIdx >= 0 ? (row[shopTypeIdx] || "") : "",
        priority: priorityIdx >= 0 ? (row[priorityIdx] || "") : "",
        status: rowStatus, // Use the trimmed status
        notes: notesIdx >= 0 ? (row[notesIdx] || "") : "",
        contact_date: contactDateIdx >= 0 ? (row[contactDateIdx] || "") : "",
        contact_method: contactMethodIdx >= 0 ? (row[contactMethodIdx] || "") : "",
        follow_up_date: followUpDateIdx >= 0 ? (row[followUpDateIdx] || "") : "",
        contact_person: contactPersonIdx >= 0 ? (row[contactPersonIdx] || "") : "",
        owner_name: ownerNameIdx >= 0 ? (row[ownerNameIdx] || "") : "",
        referral: referralIdx >= 0 ? (row[referralIdx] || "") : "",
        product_interest: productInterestIdx >= 0 ? (row[productInterestIdx] || "") : "",
        follow_up_event_link: followUpEventLinkIdx >= 0 ? (row[followUpEventLinkIdx] || "") : "",
        visit_date: visitDateIdx >= 0 ? (row[visitDateIdx] || "") : "",
        outcome: outcomeIdx >= 0 ? (row[outcomeIdx] || "") : "",
        sales_process_notes: salesNotesIdx >= 0 ? (row[salesNotesIdx] || "") : "",
        latitude: storeLat,
        longitude: storeLng,
        distance: Math.round(distance * 10) / 10 // Round to 1 decimal place
      };
      
      stores.push(store);
    }
    
    // Sort by distance
    stores.sort((a, b) => a.distance - b.distance);
    
    // Return top N stores
    return stores.slice(0, limit);
    
  } catch (error) {
    Logger.log("Error in findNearbyStores: " + error.toString());
    throw error;
  }
}

function ensureDappRemarksSheet_(spreadsheet) {
  let sheet = spreadsheet.getSheetByName(DAPP_REMARKS_SHEET);
  const headers = [
    'Submission ID',
    'Shop Name',
    'Status',
    'Remarks',
    'Submitted By',
    'Submitted At',
    'Processed',
    'Processed At'
  ];

  if (!sheet) {
    sheet = spreadsheet.insertSheet(DAPP_REMARKS_SHEET);
    sheet.appendRow(headers);
    return sheet;
  }

  const existingHeaders = sheet.getRange(1, 1, 1, headers.length).getValues()[0];
  if (existingHeaders.join('') !== headers.join('')) {
    sheet.clear();
    sheet.appendRow(headers);
  }

  return sheet;
}

function logDappSubmission_(spreadsheet, shopName, status, remarks, submittedBy, processed) {
  const sheet = ensureDappRemarksSheet_(spreadsheet);
  const submissionId = Utilities.getUuid();
  const submittedAt = new Date();
  let processedFlag;
  let processedAt = '';

  if (processed === true) {
    processedFlag = 'Yes';
    processedAt = submittedAt;
  } else if (processed === null) {
    processedFlag = 'Status Applied';
  } else {
    processedFlag = 'No';
  }
  sheet.appendRow([
    submissionId,
    shopName || '',
    status || '',
    remarks || '',
    submittedBy || '',
    submittedAt,
    processedFlag,
    processedAt
  ]);
  return submissionId;
}

/**
 * Update store status and/or shop type in the spreadsheet
 * @param {string} shopName - Name of the shop to update
 * @param {string} newStatus - New status value
 * @param {string} digitalSignature - Digital signature (public key) of the person making the change
 * @param {string} remarks - Optional remarks
 * @param {string} submittedBy - Optional submitted by identifier
 * @param {string} newShopType - Optional new shop type value
 * @return {Object} Result object with success/error
 */
function updateStoreStatus(shopName, newStatus, digitalSignature, remarks, submittedBy, newShopType) {
  try {
    const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
    const sheet = spreadsheet.getSheetByName(SHEET_NAME);
    
    if (!sheet) {
      throw new Error(`Sheet "${SHEET_NAME}" not found`);
    }
    
    // Get all data
    const data = sheet.getDataRange().getValues();
    if (data.length < 2) {
      throw new Error("No data found in sheet");
    }
    
    // Find column indices
    const headers = data[0];
    const shopNameIdx = headers.indexOf("Shop Name");
    const statusIdx = headers.indexOf("Status");
    const shopTypeIdx = headers.indexOf("Shop Type");
    const salesNotesIdx = headers.indexOf("Sales Process Notes");
    
    // Find or create "Status Updated By" column
    let statusUpdatedByIdx = headers.indexOf("Status Updated By");
    if (statusUpdatedByIdx === -1) {
      // Column doesn't exist, add it at the end
      const lastCol = headers.length;
      sheet.getRange(1, lastCol + 1).setValue("Status Updated By");
      statusUpdatedByIdx = lastCol;
      Logger.log("Created 'Status Updated By' column");
    }
    
    // Find or create "Status Updated Date" column
    let statusUpdatedDateIdx = headers.indexOf("Status Updated Date");
    if (statusUpdatedDateIdx === -1) {
      // Column doesn't exist, add it after "Status Updated By"
      const lastCol = headers.length + (statusUpdatedByIdx === headers.length ? 1 : 0);
      sheet.getRange(1, lastCol + 1).setValue("Status Updated Date");
      statusUpdatedDateIdx = lastCol;
      Logger.log("Created 'Status Updated Date' column");
    }
    
    if (shopNameIdx === -1 || statusIdx === -1) {
      throw new Error("Required columns not found in sheet");
    }
    
    // Find the shop by name (exact match)
    let found = false;
    for (let i = 1; i < data.length; i++) {
      if (data[i][shopNameIdx] === shopName) {
        const rowNum = i + 1; // Convert to 1-indexed for sheet
        
        // Update status
        sheet.getRange(rowNum, statusIdx + 1).setValue(newStatus);
        
        // Update shop type if provided
        if (newShopType && newShopType !== null && newShopType !== undefined && newShopType !== "") {
          if (shopTypeIdx === -1) {
            // Shop Type column doesn't exist, add it
            const lastCol = headers.length;
            sheet.getRange(1, lastCol + 1).setValue("Shop Type");
            const newShopTypeIdx = lastCol;
            sheet.getRange(rowNum, newShopTypeIdx + 1).setValue(newShopType);
            Logger.log("Created 'Shop Type' column and updated value");
          } else {
            sheet.getRange(rowNum, shopTypeIdx + 1).setValue(newShopType);
            Logger.log(`Updated shop type for "${shopName}" to "${newShopType}"`);
          }
        }
        
        // Update digital signature (public key)
        const submittedValue = digitalSignature || submittedBy || "";
        if (submittedValue) {
          sheet.getRange(rowNum, statusUpdatedByIdx + 1).setValue(submittedValue);
        }
        
        // Update timestamp
        const timestamp = new Date();
        sheet.getRange(rowNum, statusUpdatedDateIdx + 1).setValue(timestamp);
        
        // Append remarks into Sales Process Notes
        if (remarks && salesNotesIdx !== -1) {
          const noteRange = sheet.getRange(rowNum, salesNotesIdx + 1);
          const existingNotes = noteRange.getValue();
          const timestampIso = timestamp.toISOString();
          const noteLine = `[${timestampIso} | ${submittedValue || "DApp"}] ${remarks}`;
          const updatedNotes = existingNotes ? `${existingNotes}\n\n${noteLine}` : noteLine;
          noteRange.setValue(updatedNotes);
        }
        
        found = true;
        Logger.log(`Updated status for "${shopName}" to "${newStatus}" by ${digitalSignature || "unknown"}`);
        break;
      }
    }
    
    if (!found) {
      throw new Error(`Shop "${shopName}" not found`);
    }

    const submissionId = logDappSubmission_(spreadsheet, shopName, newStatus, remarks, digitalSignature || submittedBy, null);                                
    
    return {
      success: true,
      message: `Status updated to "${newStatus}"`,
      submissionId: submissionId
    };
  } catch (error) {
    Logger.log("Error in updateStoreStatus: " + error.toString());
    throw error;
  }
}

function addNewStore(storeData) {
  const spreadsheet = SpreadsheetApp.openById(SPREADSHEET_ID);
  const sheet = spreadsheet.getSheetByName(SHEET_NAME);
  if (!sheet) {
    throw new Error(`Sheet "${SHEET_NAME}" not found`);
  }

  let data = sheet.getDataRange().getValues();
  if (!data || data.length === 0) {
    throw new Error(`Sheet "${SHEET_NAME}" does not have a header row.`);
  }

  let headers = data[0];
  if (headers.indexOf('Store Key') === -1) {
    sheet.getRange(1, headers.length + 1).setValue('Store Key');
    data = sheet.getDataRange().getValues();
    headers = data[0];
  }

  const headerIndex = {};
  headers.forEach((header, idx) => {
    headerIndex[header] = idx;
  });

  const storeKeyIdx = headerIndex['Store Key'];
  const shopNameIdx = headerIndex['Shop Name'];
  const addressIdx = headerIndex['Address'];
  const cityIdx = headerIndex['City'];
  const stateIdx = headerIndex['State'];
  const statusIdx = headerIndex['Status'];

  if (shopNameIdx === undefined || shopNameIdx === -1) {
    throw new Error('Required column "Shop Name" not found in sheet.');
  }

  const storeKey = createStoreKey_(storeData.shopName, storeData.address, storeData.city, storeData.state);
  if (!storeKey) {
    return {
      success: false,
      error: 'Missing required fields to determine uniqueness',
      message: 'Shop name and at least one of address, city, or state are required.'
    };
  }

  for (let i = 1; i < data.length; i++) {
    const row = data[i];
    const rowShopName = row[shopNameIdx];

    if (!rowShopName) {
      continue;
    }

    const existingKeyFromColumn = storeKeyIdx >= 0 ? row[storeKeyIdx] : '';
    const fallbackKey = createStoreKey_(rowShopName, addressIdx >= 0 ? row[addressIdx] : '', cityIdx >= 0 ? row[cityIdx] : '', stateIdx >= 0 ? row[stateIdx] : '');
    const normalizedExistingKey = (existingKeyFromColumn || fallbackKey || '').toLowerCase();

    if (!existingKeyFromColumn && fallbackKey && storeKeyIdx >= 0) {
      sheet.getRange(i + 1, storeKeyIdx + 1).setValue(fallbackKey);
    }

    if (normalizedExistingKey && normalizedExistingKey === storeKey.toLowerCase()) {
      const existingStatus = statusIdx >= 0 ? (row[statusIdx] || '') : '';
      return {
        success: false,
        duplicate: true,
        message: `Store "${rowShopName}" is already on the hit list.`,
        error: 'Duplicate store detected',
        existingStore: {
          shopName: rowShopName,
          status: existingStatus,
          rowNumber: i + 1
        }
      };
    }
  }

  const row = new Array(headers.length).fill('');
  function setValue(header, value) {
    if (headerIndex.hasOwnProperty(header) && value !== undefined && value !== null) {
      row[headerIndex[header]] = value;
    }
  }

  const now = new Date();
  const submittedBy = storeData.submittedBy || 'DApp';
  const baseNote = `Added via DApp on ${now.toISOString()}${submittedBy ? ' by ' + submittedBy : ''}.`;

  const latValue = storeData.latitude ? parseFloat(storeData.latitude) : '';
  const lngValue = storeData.longitude ? parseFloat(storeData.longitude) : '';

  const salesNotes = [];
  if (storeData.remarks) {
    salesNotes.push(`[${now.toISOString()} | ${submittedBy}] ${storeData.remarks}`);
  }
  salesNotes.push(`[${now.toISOString()} | ${submittedBy}] Added via DApp.`);

  setValue('Shop Name', storeData.shopName);
  setValue('Status', storeData.status || 'Research');
  setValue('Priority', storeData.priority || 'Medium');
  setValue('Address', storeData.address || '');
  setValue('City', storeData.city || '');
  setValue('State', storeData.state || '');
  setValue('Shop Type', storeData.shopType || '');
  setValue('Phone', storeData.phone || '');
  setValue('Email', storeData.email || '');
  setValue('Website', storeData.website || '');
  setValue('Instagram', storeData.instagram || '');
  setValue('Notes', baseNote);
  setValue('Sales Process Notes', salesNotes.join('\n'));
  setValue('Latitude', !isNaN(latValue) ? latValue : '');
  setValue('Longitude', !isNaN(lngValue) ? lngValue : '');
  setValue('Contact Date', storeData.contactDate || '');
  setValue('Contact Method', storeData.contactMethod || '');
  setValue('Status Updated By', submittedBy);
  setValue('Status Updated Date', now);
  setValue('Store Key', storeKey);

  sheet.appendRow(row);

  const submissionId = logDappSubmission_(spreadsheet, storeData.shopName, storeData.status, storeData.remarks, submittedBy, true);
  return {
    success: true,
    message: `Added new store "${storeData.shopName}"`,
    submissionId: submissionId
  };
}

/**
 * Web app entry point - handles GET requests
 * @param {Object} e - Event object with parameters
 * @return {TextOutput} JSON response
 */
function doGet(e) {
  try {
    if (e.parameter.action === 'add_store') {
      const shopName = (e.parameter.shop_name || '').trim();
      if (!shopName) {
        return ContentService
          .createTextOutput(JSON.stringify({
            success: false,
            error: "Missing parameters",
            message: "shop_name is required to add a store"
          }))
          .setMimeType(ContentService.MimeType.JSON);
      }

      const storeData = {
        shopName: shopName,
        status: (e.parameter.status || 'Research').trim(),
        remarks: (e.parameter.remarks || '').trim(),
        address: (e.parameter.address || '').trim(),
        city: (e.parameter.city || '').trim(),
        state: (e.parameter.state || '').trim(),
        phone: (e.parameter.phone || '').trim(),
        email: (e.parameter.email || '').trim(),
        website: (e.parameter.website || '').trim(),
        instagram: (e.parameter.instagram || '').trim(),
        shopType: (e.parameter.shop_type || '').trim(),
        latitude: (e.parameter.latitude || '').trim(),
        longitude: (e.parameter.longitude || '').trim(),
        submittedBy: (e.parameter.submitted_by || e.parameter.digital_signature || '').trim()
      };

      let salesNotes = '';
      if (storeData.remarks) {
        salesNotes = `[${new Date().toISOString()} | ${storeData.submittedBy || 'DApp'}] ${storeData.remarks}`;
      }
      storeData.salesNotes = salesNotes;

      const result = addNewStore(storeData);
      if (result.success) {
        return ContentService
          .createTextOutput(JSON.stringify({
            success: true,
            message: result.message,
            submission_id: result.submissionId || ''
          }))
          .setMimeType(ContentService.MimeType.JSON);
      }

      return ContentService
        .createTextOutput(JSON.stringify({
          success: false,
          error: result.error || 'Unable to add store',
          message: result.message || '',
          duplicate: !!result.duplicate,
          existing_store: result.existingStore || null
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }

    // Check if this is a status update request
    if (e.parameter.action === 'update_status') {
      const shopName = e.parameter.shop_name;
      const newStatus = e.parameter.new_status;
      const newShopType = e.parameter.shop_type || '';
      const digitalSignature = e.parameter.digital_signature || e.parameter.signature || e.parameter.public_key;                                                
      const remarks = e.parameter.remarks || '';
      const submittedBy = e.parameter.submitted_by || digitalSignature || '';
      
      if (!shopName || !newStatus) {
        return ContentService
          .createTextOutput(JSON.stringify({
            success: false,
            error: "Missing parameters",
            message: "shop_name and new_status are required for status updates"
          }))
          .setMimeType(ContentService.MimeType.JSON);
      }
      
      // Update the status and/or shop type (digitalSignature is optional but recommended)
      const result = updateStoreStatus(shopName, newStatus, digitalSignature, remarks, submittedBy, newShopType);
      
      return ContentService
        .createTextOutput(JSON.stringify({
          success: true,
          message: result.message,
          submission_id: result.submissionId || ''
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // Otherwise, handle as a search request
    // Get parameters
    const lat = parseFloat(e.parameter.lat || e.parameter.latitude);
    const lng = parseFloat(e.parameter.lng || e.parameter.longitude);
    const limit = parseInt(e.parameter.limit || "10");
    // Handle status filter: can be single value or array of values
    let statusFilters = null;
    if (e.parameter.status !== undefined && e.parameter.status !== null) {
      // Check if it's an array (multiple status parameters)
      if (Array.isArray(e.parameter.status)) {
        // Filter out empty strings
        const filtered = e.parameter.status.filter(s => s !== "" && s !== "All");
        if (filtered.length > 0) {
          statusFilters = filtered;
        }
      } else {
        // Single value
        if (e.parameter.status === "" || e.parameter.status === "All") {
          statusFilters = null; // Show all
        } else {
          statusFilters = [e.parameter.status];
        }
      }
    } else {
      statusFilters = ["Contacted"]; // Default if not provided
    }
    
    // Get bounds parameters (optional, for map viewport filtering)
    let bounds = null;
    const neLat = e.parameter.ne_lat ? parseFloat(e.parameter.ne_lat) : null;
    const neLng = e.parameter.ne_lng ? parseFloat(e.parameter.ne_lng) : null;
    const swLat = e.parameter.sw_lat ? parseFloat(e.parameter.sw_lat) : null;
    const swLng = e.parameter.sw_lng ? parseFloat(e.parameter.sw_lng) : null;
    
    // Only use bounds if all four values are provided and valid
    if (neLat !== null && neLng !== null && swLat !== null && swLng !== null &&
        !isNaN(neLat) && !isNaN(neLng) && !isNaN(swLat) && !isNaN(swLng)) {
      bounds = {
        neLat: neLat,
        neLng: neLng,
        swLat: swLat,
        swLng: swLng
      };
    }
    
    // Get shop type filter: can be single value or array of values
    let shopTypeFilters = null;
    if (e.parameter.shop_type !== undefined && e.parameter.shop_type !== null) {
      // Check if it's an array (multiple shop_type parameters)
      if (Array.isArray(e.parameter.shop_type)) {
        // Filter out empty strings
        const filtered = e.parameter.shop_type.filter(s => s !== "" && s !== "All");
        if (filtered.length > 0) {
          shopTypeFilters = filtered;
        }
      } else {
        // Single value
        if (e.parameter.shop_type !== "") {
          shopTypeFilters = [e.parameter.shop_type];
        }
      }
    }
    
    Logger.log("Status filters: " + JSON.stringify(statusFilters));
    if (shopTypeFilters) {
      Logger.log("Shop type filters: " + JSON.stringify(shopTypeFilters));
    }
    if (bounds) {
      Logger.log("Bounds filter: NE(" + bounds.neLat + "," + bounds.neLng + ") SW(" + bounds.swLat + "," + bounds.swLng + ")");
    }
    
    // Validate parameters
    if (isNaN(lat) || isNaN(lng)) {
      return ContentService
        .createTextOutput(JSON.stringify({
          success: false,
          error: "Invalid parameters",
          message: "lat and lng (or latitude and longitude) are required and must be valid numbers"
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // Allow higher limit when bounds are provided (for expanded map view)
    const maxLimit = bounds ? 200 : 50;
    if (isNaN(limit) || limit < 1 || limit > maxLimit) {
      return ContentService
        .createTextOutput(JSON.stringify({
          success: false,
          error: "Invalid limit",
          message: "limit must be a number between 1 and " + maxLimit
        }))
        .setMimeType(ContentService.MimeType.JSON);
    }
    
    // Find nearby stores
    const stores = findNearbyStores(lat, lng, limit, statusFilters, bounds, shopTypeFilters);
    
    // Return JSON response
    return ContentService
      .createTextOutput(JSON.stringify({
        success: true,
        location: { latitude: lat, longitude: lng },
        status_filters: statusFilters || [],
        shop_type_filters: shopTypeFilters || [],
        count: stores.length,
        stores: stores
      }))
      .setMimeType(ContentService.MimeType.JSON);
      
  } catch (error) {
    Logger.log("Error in doGet: " + error.toString());
    return ContentService
      .createTextOutput(JSON.stringify({
        success: false,
        error: error.toString()
      }))
      .setMimeType(ContentService.MimeType.JSON);
  }
}

/**
 * Test function for status update
 * Usage: Run this function in the Apps Script editor to test the updateStoreStatus function
 */
function testUpdateStoreStatus() {
  const testShopName = "iChakras Smart Healing Center";
  const testNewStatus = "Partnered";
  
  Logger.log("Testing updateStoreStatus with:");
  Logger.log("  Shop Name: " + testShopName);
  Logger.log("  New Status: " + testNewStatus);
  Logger.log("");
  
  try {
    const result = updateStoreStatus(testShopName, testNewStatus);
    Logger.log("✅ Test successful!");
    Logger.log("Result: " + JSON.stringify(result));
    return result;
  } catch (error) {
    Logger.log("❌ Test failed: " + error.toString());
    throw error;
  }
}

/**
 * Test function - tests the actual method called by doGet
 * Usage: Run this function in the Apps Script editor to test the findNearbyStores function
 * Check View > Logs for the output
 */
function testFindNearbyStores() {
  // Test with San Francisco coordinates
  const lat = 37.7749;
  const lng = -122.4194;
  const limit = 10;
  
  // Test different status filters
  const testCases = [
    { status: "Contacted", description: "Filter by Contacted" },
    { status: "Research", description: "Filter by Research" },
    { status: null, description: "Show all statuses (null)" },
    { status: "", description: "Show all statuses (empty string)" }
  ];
  
  testCases.forEach(testCase => {
    Logger.log("=".repeat(50));
    Logger.log("Testing: " + testCase.description);
    Logger.log("  Latitude: " + lat);
    Logger.log("  Longitude: " + lng);
    Logger.log("  Limit: " + limit);
    Logger.log("  Status Filter: " + testCase.status);
    Logger.log("");
  
    try {
      const stores = findNearbyStores(lat, lng, limit, testCase.status);
    
      Logger.log("✅ Test successful!");
      Logger.log("Found " + stores.length + " stores");
      Logger.log("");
      if (stores.length > 0) {
        stores.forEach((store, index) => {
          Logger.log((index + 1) + ". " + store.name + " (Status: " + store.status + ") - " + store.distance.toFixed(2) + " miles");
        });
      } else {
        Logger.log("No stores found matching the filter.");
      }
      Logger.log("");
    } catch (error) {
      Logger.log("❌ Test failed: " + error.toString());
      Logger.log("");
    }
  });
}

/**
 * Test function - simulates doGet call with test parameters
 * Usage: Run this function in the Apps Script editor to test the full doGet flow
 * Check View > Logs for the output
 */
function testDoGet() {
  // Simulate doGet call with test parameters
  const e = {
    parameter: {
      lat: "37.7749",
      lng: "-122.4194",
      limit: "10",
      status: "Contacted"
    }
  };
  
  Logger.log("Testing doGet with parameters:");
  Logger.log("  lat: " + e.parameter.lat);
  Logger.log("  lng: " + e.parameter.lng);
  Logger.log("  limit: " + e.parameter.limit);
  Logger.log("  status: " + e.parameter.status);
  Logger.log("");
  
  try {
    const output = doGet(e);
    const responseText = output.getContent();
    const response = JSON.parse(responseText);
    
    Logger.log("✅ doGet test successful!");
    Logger.log("Response:");
    Logger.log(responseText);
    
    if (response.success) {
      Logger.log("Found " + response.count + " stores");
    } else {
      Logger.log("Error: " + response.error);
    }
    
    return response;
  } catch (error) {
    Logger.log("❌ doGet test failed: " + error.toString());
    throw error;
  }
}

/**
 * Test function - simulates status update doGet call
 * Usage: Run this function in the Apps Script editor to test the status update functionality
 * Check View > Logs for the output
 */
function testDoGetStatusUpdate() {
  // Simulate doGet call for status update
  const e = {
    parameter: {
      action: "update_status",
      shop_name: "iChakras Smart Healing Center",
      new_status: "Partnered"
    }
  };
  
  Logger.log("Testing doGet status update with parameters:");
  Logger.log("  action: " + e.parameter.action);
  Logger.log("  shop_name: " + e.parameter.shop_name);
  Logger.log("  new_status: " + e.parameter.new_status);
  Logger.log("");
  
  try {
    const output = doGet(e);
    const responseText = output.getContent();
    const response = JSON.parse(responseText);
    
    Logger.log("✅ Status update test successful!");
    Logger.log("Response:");
    Logger.log(responseText);
    
    return response;
  } catch (error) {
    Logger.log("❌ Status update test failed: " + error.toString());
    throw error;
  }
}

