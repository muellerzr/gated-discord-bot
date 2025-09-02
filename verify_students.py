"""
Directions: Run this file in a screen session with `python verify_students.py auto`

Make sure the following is set:
Environment Variables:
- `DATABASE_PATH`: Should be the same database path as with `student_verification_bot.py`
- `DISCORD_TOKEN`: Should be the same token as the one with `student_verification_bot.py`
- `maven_url`: Should be the maven URL that they provide to you for a link to all your students emails
               and names for verification
"""

import sqlite3
import os
from dotenv import load_dotenv
from datetime import datetime
import sys
import discord
import asyncio
import csv
import requests
import io

load_dotenv()

DATABASE_PATH = os.getenv('DATABASE_PATH')
DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
client = discord.Client(intents=intents)

def load_authorized_emails():
    """Load the list of authorized emails from Maven endpoint"""
    authorized_emails = set()
    maven_url = "INSERT_MAVEN_URL_THEY_GIVE_YOU_HERE"
    
    try:
        print("Downloading authorized emails from Maven endpoint...")
        response = requests.get(maven_url, timeout=30)
        response.raise_for_status()
        
        # Parse CSV from response content
        csv_content = io.StringIO(response.text)
        reader = csv.DictReader(csv_content)
        
        for row in reader:
            # The email column is named "Users → Email" in the CSV
            email_column = 'Users â\x86\x92 Email'
            if email_column in row and row[email_column]:
                authorized_emails.add(row[email_column].strip().lower())
            
        print(f"Loaded {len(authorized_emails)} authorized emails from Maven endpoint")
    except requests.exceptions.RequestException as e:
        print(f"Error downloading CSV from Maven endpoint: {e}")
    except Exception as e:
        print(f"Error parsing CSV data: {e}")
    
    return authorized_emails

async def assign_verified_role(user_id, username):
    try:
        for guild in client.guilds:
            member = guild.get_member(user_id)
            if member:
                verified_role = discord.utils.get(guild.roles, name="verified")
                print(f"Adding role to {member}")
                
                await member.add_roles(verified_role, reason="Student email verified")
                return True
        return False
    except Exception as e:
        print(f"Error assigning role: {e}")
        return False

@client.event
async def on_ready():
    print(f'Discord client connected as {client.user}')

def display_pending_students():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Load authorized emails from CSV
    authorized_emails = load_authorized_emails()
    
    # Get ALL students from database
    cursor.execute("""
        SELECT user_id, username, email, submitted_at, verified 
        FROM student_emails 
        ORDER BY submitted_at
    """)
    
    all_students = cursor.fetchall()
    
    if not all_students:
        print("No students in database.")
        conn.close()
        return
    
    # Separate students into categories
    pending_without_role = []
    verified_without_role = []
    already_have_role = []
    
    for user_id, username, email, submitted_at, verified in all_students:
        # Check if user has the verified role on Discord
        has_role = False
        if client.is_ready():
            for guild in client.guilds:
                member = guild.get_member(user_id)
                if member:
                    verified_role = discord.utils.get(guild.roles, name="verified")
                    if verified_role and verified_role in member.roles:
                        has_role = True
                        break
        
        if has_role:
            already_have_role.append((user_id, username, email, submitted_at, verified))
        elif email.lower() in authorized_emails:
            # Auto-verify if in authorized list and update database
            if not verified:
                cursor.execute(
                    "UPDATE student_emails SET verified = TRUE WHERE user_id = ?",
                    (user_id,)
                )
                print(f"✓ Auto-verified in database: {email} (from Maven endpoint)")
            verified_without_role.append((user_id, username, email, submitted_at))
        elif not verified:
            pending_without_role.append((user_id, username, email, submitted_at))
        else:
            # Verified in DB but not in CSV and no role
            verified_without_role.append((user_id, username, email, submitted_at))
    
    conn.commit()
    
    # Display summary
    print("\n" + "="*80)
    print("VERIFICATION STATUS SUMMARY")
    print("="*80)
    print(f"Total students in database: {len(all_students)}")
    print(f"Already have verified role: {len(already_have_role)}")
    print(f"Need verified role: {len(verified_without_role)}")
    print(f"Pending verification: {len(pending_without_role)}")
    
    # Show students who need roles
    if verified_without_role:
        print("\n" + "="*80)
        print("STUDENTS WHO NEED VERIFIED ROLE")
        print("="*80)
        print(f"{'#':<5} {'User ID':<20} {'Username':<25} {'Email':<30} {'Submitted':<20}")
        print("-"*80)
        
        for idx, (user_id, username, email, submitted_at) in enumerate(verified_without_role, 1):
            submitted_date = datetime.fromisoformat(submitted_at).strftime("%Y-%m-%d %H:%M")
            print(f"{idx:<5} {user_id:<20} {username:<25} {email:<30} {submitted_date:<20}")
    
    # Show pending students
    if pending_without_role:
        print("\n" + "="*80)
        print("PENDING STUDENT VERIFICATIONS (NOT IN MAVEN LIST)")
        print("="*80)
        print(f"{'#':<5} {'User ID':<20} {'Username':<25} {'Email':<30} {'Submitted':<20}")
        print("-"*80)
        
        for idx, (user_id, username, email, submitted_at) in enumerate(pending_without_role, 1):
            submitted_date = datetime.fromisoformat(submitted_at).strftime("%Y-%m-%d %H:%M")
            print(f"{idx:<5} {user_id:<20} {username:<25} {email:<30} {submitted_date:<20}")
    
    print("\n" + "="*80)
    
    # Return both lists for processing
    return conn, verified_without_role, pending_without_role

async def verify_students(conn, verified_without_role, pending_students):
    # First, automatically assign roles to verified users who don't have them
    if verified_without_role and client.is_ready():
        print("\nAutomatically assigning roles to verified students...")
        for user_id, username, email, _ in verified_without_role:
            success = await assign_verified_role(user_id, username)
            if success:
                print(f"✓ Discord role assigned to: {username}")
            else:
                print(f"✗ Could not assign Discord role to: {username} (user_id: {user_id})")
    
    # If no pending students, we're done
    if not pending_students:
        print("\nNo pending students to manually verify.")
        conn.close()
        return
    
    print("\nEnter student numbers to verify (comma-separated), 'all' to verify all, or 'exit' to quit:")
    user_input = input("> ").strip()
    
    if user_input.lower() == 'exit':
        conn.close()
        return
    
    cursor = conn.cursor()
    verified_users = []
    
    if user_input.lower() == 'all':
        for user_id, username, email, _ in pending_students:
            cursor.execute(
                "UPDATE student_emails SET verified = TRUE WHERE user_id = ?",
                (user_id,)
            )
            verified_users.append((user_id, username, email))
            print(f"✓ Database updated for: {email}")
    else:
        try:
            indices = [int(x.strip()) - 1 for x in user_input.split(',')]
            for idx in indices:
                if 0 <= idx < len(pending_students):
                    user_id, username, email, _ = pending_students[idx]
                    cursor.execute(
                        "UPDATE student_emails SET verified = TRUE WHERE user_id = ?",
                        (user_id,)
                    )
                    verified_users.append((user_id, username, email))
                    print(f"✓ Database updated for: {email}")
                else:
                    print(f"✗ Invalid index: {idx + 1}")
        except ValueError:
            print("Invalid input. Please enter numbers separated by commas.")
            conn.close()
            return
    
    conn.commit()
    conn.close()
    
    if verified_users and client.is_ready():
        print("\nAssigning Discord roles to newly verified students...")
        for user_id, username, email in verified_users:
            success = await assign_verified_role(user_id, username)
            if success:
                print(f"✓ Discord role assigned to: {username}")
            else:
                print(f"✗ Could not assign Discord role to: {username} (user_id: {user_id})")
    
    print("\nVerification complete!")

def show_all_students():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_id, username, email, submitted_at, verified
        FROM student_emails
        ORDER BY submitted_at DESC
    """)
    
    all_students = cursor.fetchall()
    
    if not all_students:
        print("No students in database.")
        conn.close()
        return
    
    print("\n" + "="*90)
    print("ALL STUDENTS")
    print("="*90)
    print(f"{'User ID':<20} {'Username':<25} {'Email':<30} {'Submitted':<20} {'Status':<10}")
    print("-"*90)
    
    for user_id, username, email, submitted_at, verified in all_students:
        submitted_date = datetime.fromisoformat(submitted_at).strftime("%Y-%m-%d %H:%M")
        status = "Verified" if verified else "Pending"
        print(f"{user_id:<20} {username:<25} {email:<30} {submitted_date:<20} {status:<10}")
    
    print("\n" + "="*90)
    conn.close()

async def auto_verify_from_csv():
    """Auto-verify all pending students whose emails are in Maven list"""
    if not os.path.exists(DATABASE_PATH):
        print(f"Database not found at {DATABASE_PATH}")
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Load authorized emails from CSV
    authorized_emails = load_authorized_emails()
    
    cursor.execute("""
        SELECT user_id, username, email, submitted_at 
        FROM student_emails 
        WHERE verified = FALSE
        ORDER BY submitted_at
    """)
    
    pending_students = cursor.fetchall()
    verified_users = []
    unverified_users = []
    
    for user_id, username, email, submitted_at in pending_students:
        if email.lower() in authorized_emails:
            cursor.execute(
                "UPDATE student_emails SET verified = TRUE WHERE user_id = ?",
                (user_id,)
            )
            verified_users.append((user_id, username, email))
            print(f"✓ Auto-verified: {email}")
        else:
            unverified_users.append((user_id, username, email))
    
    conn.commit()
    conn.close()
    
    if verified_users and client.is_ready():
        print("\nAssigning Discord roles...")
        for user_id, username, email in verified_users:
            success = await assign_verified_role(user_id, username)
            if success:
                print(f"✓ Discord role assigned to: {username}")
            else:
                print(f"✗ Could not assign Discord role to: {username} (user_id: {user_id})")
    
    # Display summary
    print(f"\nAuto-verification complete! Verified {len(verified_users)} students.")
    
    # If there are unverified users, display them and exit (non-interactive)
    if unverified_users:
        print("\n" + "="*80)
        print("STUDENTS WHO COULD NOT BE AUTO-VERIFIED (NOT IN MAVEN LIST)")
        print("="*80)
        print(f"{'Username':<25} {'Email':<40}")
        print("-"*80)
        for user_id, username, email in unverified_users:
            print(f"{username:<25} {email:<40}")
        print("="*80)
        print(f"\nTotal unverified: {len(unverified_users)} students")

async def re_verify_all():
    """Re-assign verified role to ALL students in the database (both verified and unverified)"""
    if not os.path.exists(DATABASE_PATH):
        print(f"Database not found at {DATABASE_PATH}")
        return
    
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    # Load authorized emails from CSV
    authorized_emails = load_authorized_emails()
    
    # Get ALL students from the database
    cursor.execute("""
        SELECT user_id, username, email, verified 
        FROM student_emails 
        ORDER BY username
    """)
    
    all_students = cursor.fetchall()
    
    print(f"\nFound {len(all_students)} total students in database")
    print(f"Checking against {len(authorized_emails)} authorized emails from Maven\n")
    
    eligible_users = []
    ineligible_users = []
    
    for user_id, username, email, verified in all_students:
        if email.lower() in authorized_emails:
            eligible_users.append((user_id, username, email, verified))
        else:
            ineligible_users.append((user_id, username, email, verified))
    
    print(f"ELIGIBLE FOR VERIFIED ROLE ({len(eligible_users)} students):")
    print("-" * 80)
    for user_id, username, email, verified in eligible_users:
        status = "Already Verified" if verified else "Pending"
        print(f"  {username:<25} {email:<35} [{status}]")
    
    print(f"\nNOT ELIGIBLE ({len(ineligible_users)} students):")
    print("-" * 80)
    for user_id, username, email, verified in ineligible_users:
        print(f"  {username:<25} {email:<35}")
    
    # Update database to mark all eligible users as verified
    for user_id, username, email, verified in eligible_users:
        if not verified:
            cursor.execute(
                "UPDATE student_emails SET verified = TRUE WHERE user_id = ?",
                (user_id,)
            )
            print(f"\n✓ Updated database for: {email}")
    
    conn.commit()
    conn.close()
    
    # Now assign Discord roles to ALL eligible users
    if eligible_users and client.is_ready():
        print("\n\nAssigning Discord roles to ALL eligible users...")
        print("=" * 80)
        
        success_count = 0
        fail_count = 0
        
        for user_id, username, email, _ in eligible_users:
            print(f"\nProcessing: {username} (ID: {user_id})")
            success = await assign_verified_role(user_id, username)
            if success:
                print(f"  ✓ Discord role assigned successfully")
                success_count += 1
            else:
                print(f"  ✗ Failed to assign role (user may not be in server)")
                fail_count += 1
        
        print("\n" + "=" * 80)
        print(f"SUMMARY: {success_count} successful, {fail_count} failed")
        print("=" * 80)
    else:
        print("\nDiscord client not ready or no eligible users found.")
    
    print(f"\nRe-verification complete!")

async def run_verification():
    if not os.path.exists(DATABASE_PATH):
        print(f"Database not found at {DATABASE_PATH}")
        print("Make sure the bot has run at least once to create the database.")
        return
    
    if len(sys.argv) > 1:
        if sys.argv[1] == '--all':
            show_all_students()
        elif sys.argv[1] == '--auto':
            await auto_verify_from_csv()
        elif sys.argv[1] == '--reverify':
            await re_verify_all()
        elif sys.argv[1] == '--help':
            print("Usage:")
            print("  python verify_students.py          # Interactive verification")
            print("  python verify_students.py --all    # Show all students")
            print("  python verify_students.py --auto   # Auto-verify from Maven list")
            print("  python verify_students.py --reverify # Re-assign role to ALL eligible students")
    else:
        result = display_pending_students()
        if result:
            conn, verified_without_role, pending_students = result
            await verify_students(conn, verified_without_role, pending_students)

async def main():
    await client.login(DISCORD_TOKEN)
    asyncio.create_task(client.connect())
    
    while not client.is_ready():
        await asyncio.sleep(1)
    
    await run_verification()
    await client.close()

if __name__ == "__main__":
    asyncio.run(main())
