# Market Research Repository

This repository contains tools and data for managing **multi-channel content marketing** and **physical store partnerships** for Agroverse.shop and TrueSight DAO.

**Secrets:** Do not commit API keys, OAuth tokens, or service account JSON. See **[`SECURITY.md`](SECURITY.md)** and **`.gitignore`**.

## 📁 Repository Structure

```
market_research/
├── README.md                          # This file
├── requirements.txt                   # Python dependencies
├── google_credentials.json            # Google Sheets API credentials (not in repo)
├── venv/                              # Python virtual environment
│
├── physical_stores/                   # Physical store partnership management
│   ├── README.md                      # Complete physical stores guide
│   ├── data/                          # Hit List CSV data
│   ├── generate_shop_list.py          # Generate shop lists
│   ├── process_dapp_remarks.py        # Process DApp remarks
│   └── [See physical_stores/README.md for full structure]
│
├── ceremonial_cacao_seo/               # USA ceremonial cacao competitor SEO research
│   ├── README.md                       # Task context, workflow, Playwright scripts
│   ├── competitors_list.json            # Top 10 USA competitors (from search or manual)
│   ├── competitor_analysis.json        # Crawl output (titles, meta, h1, snippets)
│   ├── positioning_summary.md          # Positioning summary from crawl
│   ├── seo_keyword_strategy.md         # Match + differentiate keyword strategy
│   ├── implementation_checklist.md     # Apply to agroverse.shop + run tests
│   └── playwright/                     # Search, crawl, analyze scripts (Node/Playwright)
│
└── online_content/                     # Online content management
    ├── agroverse_shop/
    │   ├── social_media/              # Instagram content management
    │   │   ├── README.md              # Complete social media guide
    │   │   ├── sync_content_schedule.py
    │   │   ├── sync_hashtags.py
    │   │   └── [See online_content/agroverse_shop/social_media/README.md]
    │   │
    │   └── blog_post/                 # Blog content management
    │       ├── README.md               # Complete blog guide
    │       ├── sync_blog_schedule.py
    │       ├── create_blog_drafts.py
    │       └── [See online_content/agroverse_shop/blog_post/README.md]
    │
    └── truesight_dao/
        └── blog_post/                  # Truesight DAO blog management
            ├── README.md               # Truesight DAO blog guide
            ├── sync_truesight_blog_schedule.py
            └── [See online_content/truesight_dao/blog_post/README.md]
```

## 🚀 Quick Start

### 1. Setup Virtual Environment

```bash
cd /Users/garyjob/Applications/market_research
source venv/bin/activate  # On macOS/Linux
pip install -r requirements.txt
```

### 2. Google Sheets API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing one
3. Enable Google Sheets API and Google Drive API
4. Create a Service Account
5. Download the JSON credentials file
6. Rename it to `google_credentials.json` and place it in the repository root
7. Share your Google Sheets documents with the service account email

### 3. Navigate to Specific Areas

**Physical Stores:**
```bash
cd physical_stores
# See physical_stores/README.md for complete guide
```

**Agroverse Social Media:**
```bash
cd online_content/agroverse_shop/social_media
# See online_content/agroverse_shop/social_media/README.md for complete guide
```

**Agroverse Blog:**
```bash
cd online_content/agroverse_shop/blog_post
# See online_content/agroverse_shop/blog_post/README.md for complete guide
```

**Truesight DAO Blog:**
```bash
cd online_content/truesight_dao/blog_post
# See online_content/truesight_dao/blog_post/README.md for complete guide
```

## 📊 Key Google Sheets

### Physical Stores
- **Spreadsheet ID**: `1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc`
- **Worksheets**: "Hit List", "DApp Remarks"
- **Link**: [Holistic Wellness Hit List](https://docs.google.com/spreadsheets/d/1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc/edit)

### Online Content (Agroverse)
- **Spreadsheet ID**: `1ghZXeMqFq97Vl6yLKrtDmMQdQkd-4EN5yQs34NA_sBQ`
- **Worksheets**: "Content schedule", "Blog Content Schedule", "Hashtag suggestions", "Feedback on Content"
- **Link**: [Content Marketing Schedule](https://docs.google.com/spreadsheets/d/1ghZXeMqFq97Vl6yLKrtDmMQdQkd-4EN5yQs34NA_sBQ/edit)

## 🎯 Main Workflows

### Physical Stores
1. **Research & Targeting** - Identify potential partner stores
2. **Data Management** - Maintain Hit List in Google Sheets
3. **Store Visits** - In-person approach protocol
4. **Email Outreach** - Pre/post-visit communication
5. **Route Optimization** - Plan efficient visit routes
6. **Follow-up Management** - Track and schedule follow-ups

**See:** `physical_stores/README.md` for complete guide

### Agroverse Social Media
1. **Content Scheduling** - Plan Instagram content
2. **Hashtag Strategy** - Manage hashtag database
3. **Community Feedback** - Process and incorporate feedback
4. **Voice Feedback** - Capture ideas via iPhone/Siri
5. **Content Creation** - AI-assisted content workflows

**See:** `online_content/agroverse_shop/social_media/README.md` for complete guide

### Agroverse Blog
1. **Blog Scheduling** - Plan blog content
2. **Wix Integration** - Create and publish drafts
3. **SEO Optimization** - Optimize for search
4. **Instagram Integration** - Cross-promote content

**See:** `online_content/agroverse_shop/blog_post/README.md` for complete guide

### Ceremonial Cacao SEO (USA competitors)
1. **Search** – Find top 10 USA ceremonial cacao competitors (Playwright or manual).
2. **Crawl** – Extract titles, meta, H1s, snippets from competitor sites.
3. **Strategy** – Define match + differentiate keyword strategy; implement on agroverse.shop.
4. **Tests** – Run agroverse_shop Playwright tests (including SEO content alignment).

**See:** `ceremonial_cacao_seo/README.md` for full workflow and scripts.

### Truesight DAO Blog
1. **Blog Scheduling** - Plan DAO blog content
2. **Content Management** - Track and publish posts

**See:** `online_content/truesight_dao/blog_post/README.md` for complete guide

## 🔑 Key Concepts

### Primary Key Systems

**Physical Stores:**
- Shop Name matching for Hit List updates

**Content Schedules:**
- Instagram: `Post Day + Post Type + Theme`
- Blog: `Publish Date + Blog Title`

**Critical**: Changing these fields changes the primary key, which affects status preservation.

### Status Preservation

- **NEVER override status values** in Google Sheets
- Status values represent manual work and must be preserved
- Sync scripts automatically preserve status using primary key matching

## 🛠️ Common Tasks

### Pull Latest Data
```bash
# Physical stores
cd physical_stores
python3 pull_hit_list.py

# Social media (if needed)
cd online_content/agroverse_shop/social_media
python3 sync_content_schedule.py  # This syncs TO sheets, not FROM
```

### Process DApp Remarks
```bash
cd physical_stores
python3 process_dapp_remarks.py
```

### Sync Content Schedules
```bash
# Instagram
cd online_content/agroverse_shop/social_media
python3 sync_content_schedule.py

# Blog
cd online_content/agroverse_shop/blog_post
python3 sync_blog_schedule.py
```

### Process Feedback
```bash
cd online_content/agroverse_shop/social_media
python3 sync_feedback.py download
python3 process_feedback.py
python3 sync_feedback.py upload
```

## 📚 Documentation

Each subdirectory contains a comprehensive README.md that consolidates all relevant documentation:

- **`physical_stores/README.md`** - Complete physical stores guide
- **`online_content/agroverse_shop/social_media/README.md`** - Complete social media guide
- **`online_content/agroverse_shop/blog_post/README.md`** - Complete blog guide
- **`ceremonial_cacao_seo/README.md`** - Ceremonial cacao USA competitor SEO research (Playwright workflow)
- **`online_content/truesight_dao/blog_post/README.md`** - Truesight DAO blog guide

## 🔐 Security Notes

- `google_credentials.json` is in `.gitignore` and should never be committed
- Keep your Google Sheets API credentials secure
- Only share the Google Sheets documents with necessary team members
- The service account should have minimal required permissions

## 🐛 Troubleshooting

### Common Issues

1. **"google_credentials.json not found"**
   - Ensure the credentials file is in the repository root
   - Check file permissions

2. **"Permission denied" errors**
   - Verify the service account has access to the Google Sheets documents
   - Check API permissions in Google Cloud Console

3. **"Worksheet not found"**
   - Ensure worksheet names match exactly
   - Check if worksheets exist in the Google Sheets documents

4. **Status not preserved**
   - Check if primary key changed due to content modifications
   - Verify primary key generation logic

## 📈 Usage Tips

1. **Regular Syncs** - Run sync scripts after updating CSV files
2. **Backup** - Keep local copies of your CSV files
3. **Version Control** - Commit CSV changes to track updates
4. **Testing** - Test syncs with small data sets first
5. **Documentation** - Refer to subdirectory READMEs for detailed guides

## 🔗 Links

- **GitHub Repository**: [TrueSightDAO/go_to_market](https://github.com/TrueSightDAO/go_to_market)
- [Physical Stores Hit List](https://docs.google.com/spreadsheets/d/1eiqZr3LW-qEI6Hmy0Vrur_8flbRwxwA7jXVrbUnHbvc/edit)
- [Content Marketing Schedule](https://docs.google.com/spreadsheets/d/1ghZXeMqFq97Vl6yLKrtDmMQdQkd-4EN5yQs34NA_sBQ/edit)
- [Google Cloud Console](https://console.cloud.google.com/)
- [Google Sheets API Documentation](https://developers.google.com/sheets/api)

---

*Last updated: November 2025*
*This repository is organized by functional area for easy navigation and maintenance*
*GitHub: [TrueSightDAO/go_to_market](https://github.com/TrueSightDAO/go_to_market)*
