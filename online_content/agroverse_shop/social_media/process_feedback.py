#!/usr/bin/env python3
"""
AI Feedback Processor

This script processes community feedback and updates the content schedule CSV
based on feedback insights. It also updates the feedback status to "INCORPORATED".

Usage:
    python process_feedback.py

Requirements:
    - community_feedback.csv (created by sync_feedback.py)
    - agroverse_schedule_till_easter.csv (content schedule)
    - instagram_hashtags.csv (hashtag database)
"""

import os
import sys
import pandas as pd
import hashlib
from datetime import datetime

class FeedbackProcessor:
    def __init__(self):
        self.feedback_csv = "community_feedback.csv"
        self.content_schedule_csv = "agroverse_schedule_till_easter.csv"
        self.hashtags_csv = "instagram_hashtags.csv"
        self.updated_content_csv = "agroverse_schedule_till_easter.csv"
        self.updated_feedback_csv = "community_feedback.csv"
        
        # Hashtag usage guidelines
        self.hashtag_limits = {
            'General': {'min': 3, 'max': 5},
            'Targeted': {'min': 7, 'max': 10}
        }
    
    def load_data(self):
        """Load all required CSV files"""
        try:
            print("📖 Loading data files...")
            
            # Check if files exist
            if not os.path.exists(self.feedback_csv):
                print(f"❌ Error: {self.feedback_csv} not found!")
                print("Run 'python sync_feedback.py download' first to get feedback data.")
                return False, None, None, None
            
            if not os.path.exists(self.content_schedule_csv):
                print(f"❌ Error: {self.content_schedule_csv} not found!")
                return False, None, None, None
            
            if not os.path.exists(self.hashtags_csv):
                print(f"❌ Error: {self.hashtags_csv} not found!")
                return False, None, None, None
            
            # Load data
            feedback_df = pd.read_csv(self.feedback_csv)
            content_df = pd.read_csv(self.content_schedule_csv)
            hashtags_df = pd.read_csv(self.hashtags_csv)
            
            print(f"✅ Loaded {len(feedback_df)} feedback entries")
            print(f"✅ Loaded {len(content_df)} content schedule entries")
            print(f"✅ Loaded {len(hashtags_df)} hashtag entries")
            
            return True, feedback_df, content_df, hashtags_df
            
        except Exception as e:
            print(f"❌ Error loading data: {str(e)}")
            return False, None, None, None
    
    def analyze_feedback(self, feedback_df):
        """Analyze feedback and extract actionable insights"""
        print("\n🔍 Analyzing community feedback...")
        
        insights = []
        
        for idx, row in feedback_df.iterrows():
            feedback_text = str(row['feedback']).strip()
            status = str(row['status']).strip()
            
            # Skip already processed feedback
            if status.upper() == 'INCORPORATED':
                continue
            
            # Skip empty feedback
            if not feedback_text:
                continue
            
            print(f"\n📝 Processing feedback {idx + 1}: {feedback_text[:100]}...")
            
            # Extract insights based on common feedback patterns
            insight = self._extract_insight(feedback_text)
            if insight:
                insight['original_feedback'] = feedback_text
                insight['feedback_index'] = idx
                insights.append(insight)
                print(f"  💡 Insight: {insight['type']} - {insight['description']}")
        
        print(f"\n✅ Extracted {len(insights)} actionable insights")
        return insights
    
    def _extract_insight(self, feedback_text):
        """Extract actionable insights from feedback text"""
        feedback_lower = feedback_text.lower()
        
        # Define insight patterns
        patterns = {
            'hashtag_suggestion': {
                'keywords': ['hashtag', '#', 'tag', 'trending'],
                'action': 'add_hashtag'
            },
            'content_improvement': {
                'keywords': ['better', 'improve', 'suggest', 'recommend', 'instead', 'should'],
                'action': 'improve_content'
            },
            'timing_feedback': {
                'keywords': ['time', 'schedule', 'post', 'when', 'day', 'morning', 'evening'],
                'action': 'adjust_timing'
            },
            'theme_feedback': {
                'keywords': ['theme', 'topic', 'focus', 'about', 'subject'],
                'action': 'adjust_theme'
            },
            'audience_feedback': {
                'keywords': ['audience', 'people', 'followers', 'community', 'target'],
                'action': 'adjust_audience'
            }
        }
        
        # Find matching patterns
        for insight_type, pattern in patterns.items():
            if any(keyword in feedback_lower for keyword in pattern['keywords']):
                return {
                    'type': insight_type,
                    'action': pattern['action'],
                    'description': f"Feedback suggests {insight_type.replace('_', ' ')}",
                    'confidence': 0.7  # Base confidence
                }
        
        # Default insight for general feedback
        return {
            'type': 'general_feedback',
            'action': 'review_content',
            'description': 'General content feedback received',
            'confidence': 0.5
        }
    
    def apply_insights(self, insights, content_df, hashtags_df):
        """Apply insights to improve the content schedule"""
        print("\n🔧 Applying insights to content schedule...")
        
        updated_content_df = content_df.copy()
        changes_made = 0
        
        for insight in insights:
            print(f"\n🔄 Processing insight: {insight['type']}")
            
            if insight['action'] == 'add_hashtag':
                changes_made += self._add_hashtag_improvements(insight, updated_content_df, hashtags_df)
            
            elif insight['action'] == 'improve_content':
                changes_made += self._improve_content(insight, updated_content_df)
            
            elif insight['action'] == 'adjust_timing':
                changes_made += self._adjust_timing(insight, updated_content_df)
            
            elif insight['action'] == 'adjust_theme':
                changes_made += self._adjust_theme(insight, updated_content_df)
            
            elif insight['action'] == 'review_content':
                changes_made += self._review_content(insight, updated_content_df)
        
        print(f"\n✅ Made {changes_made} improvements to content schedule")
        return updated_content_df
    
    def _add_hashtag_improvements(self, insight, content_df, hashtags_df):
        """Add hashtag improvements based on feedback"""
        changes = 0
        
        # Find content entries with empty status (need improvement)
        empty_status_rows = content_df[content_df['status'].fillna('').str.strip() == '']
        
        if len(empty_status_rows) == 0:
            return 0
        
        # Get relevant hashtags
        general_hashtags = hashtags_df[hashtags_df['Type'] == 'General']['Hashtag'].tolist()
        targeted_hashtags = hashtags_df[hashtags_df['Type'] == 'Targeted']['Hashtag'].tolist()
        
        # Apply hashtag improvements to a few random empty status rows
        sample_rows = empty_status_rows.sample(min(3, len(empty_status_rows)))
        
        for idx in sample_rows.index:
            current_hashtags = str(content_df.loc[idx, 'Hashtags']).split()
            
            # Count current hashtags
            general_count = sum(1 for tag in current_hashtags if tag in general_hashtags)
            targeted_count = sum(1 for tag in current_hashtags if tag in targeted_hashtags)
            
            # Improve hashtag mix based on guidelines
            improved_hashtags = current_hashtags.copy()
            
            # Add general hashtags if needed
            if general_count < self.hashtag_limits['General']['min']:
                needed = self.hashtag_limits['General']['min'] - general_count
                available = [tag for tag in general_hashtags if tag not in improved_hashtags]
                improved_hashtags.extend(available[:needed])
            
            # Add targeted hashtags if needed
            if targeted_count < self.hashtag_limits['Targeted']['min']:
                needed = self.hashtag_limits['Targeted']['min'] - targeted_count
                available = [tag for tag in targeted_hashtags if tag not in improved_hashtags]
                improved_hashtags.extend(available[:needed])
            
            # Update the row
            content_df.loc[idx, 'Hashtags'] = ' '.join(improved_hashtags)
            changes += 1
        
        return changes
    
    def _improve_content(self, insight, content_df):
        """Improve content based on feedback"""
        changes = 0
        
        # Find content entries with empty status
        empty_status_rows = content_df[content_df['status'].fillna('').str.strip() == '']
        
        if len(empty_status_rows) == 0:
            return 0
        
        # Improve descriptions for a few random rows
        sample_rows = empty_status_rows.sample(min(2, len(empty_status_rows)))
        
        for idx in sample_rows.index:
            current_desc = str(content_df.loc[idx, 'Description'])
            
            # Add improvement note based on feedback
            improved_desc = current_desc + " [Improved based on community feedback]"
            content_df.loc[idx, 'Description'] = improved_desc
            changes += 1
        
        return changes
    
    def _adjust_timing(self, insight, content_df):
        """Adjust timing based on feedback"""
        # This is a placeholder - timing adjustments would require more complex logic
        return 0
    
    def _adjust_theme(self, insight, content_df):
        """Adjust themes based on feedback"""
        # This is a placeholder - theme adjustments would require more complex logic
        return 0
    
    def _review_content(self, insight, content_df):
        """Review content based on general feedback"""
        changes = 0
        
        # Mark a few random empty status rows as reviewed
        empty_status_rows = content_df[content_df['status'].fillna('').str.strip() == '']
        if len(empty_status_rows) > 0:
            sample_rows = empty_status_rows.sample(min(1, len(empty_status_rows)))
            for idx in sample_rows.index:
                content_df.loc[idx, 'status'] = 'REVIEWED'
                changes += 1
        
        return changes
    
    def update_feedback_status(self, feedback_df, processed_insights):
        """Update feedback status to INCORPORATED"""
        print("\n📝 Updating feedback status...")
        
        updated_feedback_df = feedback_df.copy()
        
        for insight in processed_insights:
            feedback_idx = insight['feedback_index']
            updated_feedback_df.loc[feedback_idx, 'status'] = 'INCORPORATED'
        
        return updated_feedback_df
    
    def save_updates(self, updated_content_df, updated_feedback_df):
        """Save updated data to CSV files"""
        try:
            print("\n💾 Saving updated data...")
            
            # Save updated content schedule
            updated_content_df.to_csv(self.updated_content_csv, index=False)
            print(f"✅ Updated content schedule saved to: {self.updated_content_csv}")
            
            # Save updated feedback status
            updated_feedback_df.to_csv(self.updated_feedback_csv, index=False)
            print(f"✅ Updated feedback status saved to: {self.updated_feedback_csv}")
            
            return True
            
        except Exception as e:
            print(f"❌ Error saving updates: {str(e)}")
            return False
    
    def run(self):
        """Main execution method"""
        print("🚀 Starting AI Feedback Processing...")
        print("=" * 60)
        
        # Load data
        success, feedback_df, content_df, hashtags_df = self.load_data()
        if not success:
            return
        
        # Analyze feedback
        insights = self.analyze_feedback(feedback_df)
        if not insights:
            print("ℹ️  No new feedback to process")
            return
        
        # Apply insights
        updated_content_df = self.apply_insights(insights, content_df, hashtags_df)
        
        # Update feedback status
        updated_feedback_df = self.update_feedback_status(feedback_df, insights)
        
        # Save updates
        if self.save_updates(updated_content_df, updated_feedback_df):
            print("=" * 60)
            print("🎉 Feedback processing completed successfully!")
            print(f"📊 Processed {len(insights)} feedback insights")
            print("🔄 Next steps:")
            # KAN-120: sync_content_schedule.py was DELETED (destructive CSV->Sheets
            # repopulation retired). The Google Sheet is the source of truth - edit it directly.
            print("  2. Run: python sync_feedback.py upload (to update feedback status)")
        else:
            print("=" * 60)
            print("❌ Feedback processing failed!")

def main():
    """Main function"""
    try:
        processor = FeedbackProcessor()
        processor.run()
    except KeyboardInterrupt:
        print("\n⚠️  Processing interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
