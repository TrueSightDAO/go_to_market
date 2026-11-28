"""
Restructure unscheduled Instagram content to optimal posting days
Based on Instagram analytics: Tuesday, Thursday, Friday 12-3 PM are peak engagement times

This script:
1. Preserves all content up to and including October 12, 2025 (already scheduled)
2. Redistributes content AFTER October 12, 2025 to Tuesday/Thursday/Friday pattern
3. Considers seasonal events and festivities when scheduling
4. Updates Post Day and Day of Week columns
5. Maintains all other content (captions, themes, etc.)
6. Primary keys will change for restructured content (expected)
"""

import csv
from datetime import datetime, timedelta
import sys

# Configuration
OPTIMAL_DAYS = ['Tuesday', 'Thursday', 'Friday']
CUTOFF_DATE = datetime(2025, 10, 12)  # Only restructure content AFTER this date
INPUT_FILE = 'agroverse_schedule_till_easter_cleaned.csv'
OUTPUT_FILE = 'agroverse_schedule_till_easter_cleaned.csv'  # Overwrite original
BACKUP_FILE = 'agroverse_schedule_till_easter_cleaned_backup.csv'

# Special event dates to consider (keep on specific days if possible)
SPECIAL_EVENTS = {
    'Halloween': datetime(2025, 10, 31),
    'Thanksgiving': datetime(2025, 11, 27),
    'Black Friday': datetime(2025, 11, 28),
    'Cyber Monday': datetime(2025, 12, 1),
    'Christmas Eve': datetime(2025, 12, 24),
    'Christmas': datetime(2025, 12, 25),
    'New Years Eve': datetime(2025, 12, 31),
    'New Years': datetime(2026, 1, 1),
    'Valentines': datetime(2026, 2, 14),
    'Easter': datetime(2026, 4, 5)  # Easter 2026
}

def is_near_special_event(date, days_before=3, days_after=1):
    """Check if date is near a special event"""
    for event_name, event_date in SPECIAL_EVENTS.items():
        if event_date - timedelta(days=days_before) <= date <= event_date + timedelta(days=days_after):
            return event_name
    return None

def get_next_optimal_day(current_date, optimal_days=['Tuesday', 'Thursday', 'Friday']):
    """Find the next Tuesday, Thursday, or Friday"""
    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    
    for i in range(1, 8):
        next_date = current_date + timedelta(days=i)
        day_name = next_date.strftime('%A')
        if day_name in optimal_days:
            return next_date
    
    return current_date + timedelta(days=1)

def should_keep_on_event_day(row, post_date):
    """Determine if content should stay on its original day due to event timing"""
    theme = row.get('Theme', '').lower()
    theme_focus = row.get('Theme Focus', '').lower()
    description = row.get('Description', '').lower()
    
    # Check for event-specific keywords
    event_keywords = {
        'halloween': ['halloween', 'spooky', 'trick', 'treat'],
        'thanksgiving': ['thanksgiving', 'grateful', 'gratitude', 'thanks'],
        'christmas': ['christmas', 'holiday', 'festive', 'santa', 'gift'],
        'new year': ['new year', 'resolution', 'countdown'],
        'valentine': ['valentine', 'love', 'heart'],
        'easter': ['easter', 'spring', 'renewal']
    }
    
    content_text = f"{theme} {theme_focus} {description}".lower()
    
    for event, keywords in event_keywords.items():
        if any(keyword in content_text for keyword in keywords):
            event_date = None
            for event_name, date in SPECIAL_EVENTS.items():
                if event in event_name.lower():
                    event_date = date
                    break
            
            if event_date:
                # If within 3 days of event, keep on original day
                days_diff = abs((post_date - event_date).days)
                if days_diff <= 3:
                    return True
    
    return False

def restructure_schedule():
    """Main restructuring function"""
    
    # Create backup
    import shutil
    shutil.copy(INPUT_FILE, BACKUP_FILE)
    print(f'💾 Backup created: {BACKUP_FILE}')
    
    # Read CSV
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    print(f'\n📖 Read {len(rows)} total posts from {INPUT_FILE}')
    print('=' * 70)
    
    # Separate content by date
    preserve_rows = []  # Content to preserve (before/on cutoff)
    restructure_rows = []  # Content to restructure (after cutoff)
    
    for row in rows:
        post_day = row.get('Post Day', '')
        try:
            post_date = datetime.strptime(post_day, '%Y%m%d')
            
            # Preserve if before/on cutoff date
            if post_date <= CUTOFF_DATE:
                preserve_rows.append(row)
            else:
                restructure_rows.append(row)
        except:
            # If can't parse date, preserve it
            preserve_rows.append(row)
    
    print(f'✅ Preserving {len(preserve_rows)} posts (on or before Oct 12, 2025)')
    print(f'🔄 Restructuring {len(restructure_rows)} posts (after Oct 12, 2025)')
    
    if len(restructure_rows) == 0:
        print('\n⚠️  No posts to restructure!')
        return False
    
    # Start from first optimal day after cutoff
    current_date = CUTOFF_DATE + timedelta(days=1)
    while current_date.strftime('%A') not in OPTIMAL_DAYS:
        current_date += timedelta(days=1)
    
    print(f'\n📍 First optimal posting date: {current_date.strftime("%A, %B %d, %Y")}')
    print(f'📅 Estimated completion: ~{len(restructure_rows) // 3} weeks ({len(restructure_rows)} posts ÷ 3 days/week)')
    
    # Restructure posts
    week_counter = 1
    week_start = current_date
    posts_this_week = 0
    event_adjustments = 0
    
    for i, row in enumerate(restructure_rows):
        original_post_day = row.get('Post Day', '')
        try:
            original_date = datetime.strptime(original_post_day, '%Y%m%d')
        except:
            original_date = current_date
        
        # Check if this content is event-specific and should stay near its original date
        if should_keep_on_event_day(row, original_date):
            event_name = is_near_special_event(original_date, days_before=3, days_after=1)
            if event_name:
                print(f'   🎃 Keeping post near {event_name} ({original_date.strftime("%b %d")}): {row.get("Theme", "")}')
                # Keep original date but adjust to nearest optimal day if needed
                if original_date.strftime('%A') not in OPTIMAL_DAYS:
                    # Find nearest optimal day
                    before = original_date
                    after = original_date
                    for j in range(1, 4):
                        before = original_date - timedelta(days=j)
                        after = original_date + timedelta(days=j)
                        if before.strftime('%A') in OPTIMAL_DAYS:
                            current_date = before
                            break
                        if after.strftime('%A') in OPTIMAL_DAYS:
                            current_date = after
                            break
                else:
                    current_date = original_date
                event_adjustments += 1
        
        # Assign to current optimal day
        row['Post Day'] = current_date.strftime('%Y%m%d')
        row['Day of Week'] = current_date.strftime('%A')
        
        # Update week information
        posts_this_week += 1
        if posts_this_week == 1:
            week_start = current_date
        
        week_end = week_start + timedelta(days=6)
        row['Date Range'] = f'{week_start.strftime("%b %d")}-{week_end.strftime("%b %d, %Y")}'
        row['Week'] = f'Week {week_counter}'
        
        # Move to next optimal day
        if posts_this_week >= 3:
            posts_this_week = 0
            week_counter += 1
        
        current_date = get_next_optimal_day(current_date, OPTIMAL_DAYS)
    
    print(f'\n🎃 Made {event_adjustments} adjustments for seasonal events/festivities')
    
    # Combine preserved and restructured
    all_rows = preserve_rows + restructure_rows
    
    # Sort by Post Day
    all_rows.sort(key=lambda r: r.get('Post Day', ''))
    
    # Write output
    with open(OUTPUT_FILE, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        
        # Clean rows to only include valid fieldnames
        for row in all_rows:
            # Remove any None keys
            cleaned_row = {k: v for k, v in row.items() if k is not None and k in fieldnames}
            writer.writerow(cleaned_row)
    
    print(f'\n✅ Restructured schedule written to {OUTPUT_FILE}')
    
    # Analyze new distribution
    from collections import Counter
    new_day_counts = Counter()
    restructured_day_counts = Counter()
    
    for row in all_rows:
        day = row.get('Day of Week', '')
        if day:
            new_day_counts[day] += 1
    
    for row in restructure_rows:
        day = row.get('Day of Week', '')
        if day:
            restructured_day_counts[day] += 1
    
    print(f'\n📊 NEW SCHEDULE DISTRIBUTION (Restructured posts only):')
    print('=' * 70)
    day_order = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
    for day in day_order:
        if day in restructured_day_counts:
            marker = '✅' if day in OPTIMAL_DAYS else '⚠️ '
            print(f'   {marker} {day:12} {restructured_day_counts[day]:3} posts')
    
    print(f'\n🎯 Optimal day coverage (restructured posts):')
    for day in OPTIMAL_DAYS:
        count = restructured_day_counts.get(day, 0)
        percentage = (count / len(restructure_rows) * 100) if restructure_rows else 0
        print(f'   {day:12} {count:3} posts ({percentage:.1f}%)')
    
    print(f'\n📝 Next steps:')
    print(f'   1. Review {OUTPUT_FILE} for accuracy')
    print(f'   2. CSV only - the Sheet is the source of truth (KAN-120); edit it directly')
    print(f'   3. Backup available at: {BACKUP_FILE}')
    
    return True

if __name__ == '__main__':
    try:
        success = restructure_schedule()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f'\n❌ Error: {e}')
        import traceback
        traceback.print_exc()
        sys.exit(1)
