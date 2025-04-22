from flask import Flask, render_template, request, redirect, flash, url_for, jsonify
from flask_sqlalchemy import SQLAlchemy
import random
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
from datetime import datetime, timedelta
# Update the import to include text
from sqlalchemy import func, inspect, text
from flask import send_from_directory, jsonify, Response
app = Flask(__name__)

# Configure the database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///bookings.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = os.urandom(24)

# Initialize database
db = SQLAlchemy(app)

# Define models
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), nullable=False)
    sport = db.Column(db.String(50), nullable=False)
    slot_time = db.Column(db.String(50), nullable=False)
    ticket_id = db.Column(db.String(10), unique=True, nullable=False)
    date = db.Column(db.DateTime, default=datetime.now)
    attended = db.Column(db.Boolean, default=False)
    sent_to_controller = db.Column(db.Boolean, default=False)  # New field to track controller status

class SlotCapacity(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sport = db.Column(db.String(50), nullable=False)
    day = db.Column(db.String(20), nullable=False)
    time = db.Column(db.String(10), nullable=False)
    max_capacity = db.Column(db.Integer, nullable=False)

# Function to check if a column exists in a table
def column_exists(table_name, column_name):
    inspector = inspect(db.engine)
    columns = inspector.get_columns(table_name)
    return any(column['name'] == column_name for column in columns)

# Updated function to add column if it doesn't exist - using SQLAlchemy 2.x syntax
def add_column_if_not_exists():
    with app.app_context():
        # Check if the column exists
        if not column_exists('booking', 'sent_to_controller'):
            # Add the column using the newer SQLAlchemy syntax
            with db.engine.connect() as connection:
                connection.execute(text('ALTER TABLE booking ADD COLUMN sent_to_controller BOOLEAN DEFAULT FALSE'))
                connection.commit()
            print("Added sent_to_controller column to booking table")

# Dummy OTP storage
otp_storage = {}


MAILTRAP_SMTP_HOST = os.getenv("MAILTRAP_SMTP_HOST")
MAILTRAP_SMTP_PORT = int(os.getenv("MAILTRAP_SMTP_PORT"))
MAILTRAP_SMTP_USER = os.getenv("MAILTRAP_SMTP_USER")
MAILTRAP_SMTP_PASSWORD = os.getenv("MAILTRAP_SMTP_PASSWORD")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")

# List of allowed controller emails
ALLOWED_CONTROLLER_EMAILS = ['controller1@example.com', 'controller2@example.com', 'controller3@example.com']

# Function to initialize slot capacities
def initialize_slot_capacities():
    # Check if capacities are already set
    if SlotCapacity.query.count() > 0:
        return
    
    # Sport capacities
    capacities = {
        'Cricket': 24,
        'Badminton': 40,
        'Tennis': 10
    }
    
    # Cricket slots
    cricket_weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    cricket_weekday_times = ['6am', '4pm']
    cricket_sunday = ['Sunday']
    cricket_sunday_times = ['6am', '12pm', '6pm']
    
    # Add Cricket capacities
    for day in cricket_weekdays:
        for time in cricket_weekday_times:
            db.session.add(SlotCapacity(sport='Cricket', day=day, time=time, max_capacity=capacities['Cricket']))
    
    for day in cricket_sunday:
        for time in cricket_sunday_times:
            db.session.add(SlotCapacity(sport='Cricket', day=day, time=time, max_capacity=capacities['Cricket']))
    
    # Badminton and Tennis slots
    racket_weekdays = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    racket_weekday_times = ['5am', '7am', '9am', '2pm', '9pm']
    racket_weekend = ['Saturday', 'Sunday']
    racket_weekend_times = ['4pm', '6pm']
    
    # Add Badminton capacities
    for day in racket_weekdays:
        for time in racket_weekday_times:
            db.session.add(SlotCapacity(sport='Badminton', day=day, time=time, max_capacity=capacities['Badminton']))
    
    for day in racket_weekend:
        for time in racket_weekend_times:
            db.session.add(SlotCapacity(sport='Badminton', day=day, time=time, max_capacity=capacities['Badminton']))
    
    # Add Tennis capacities
    for day in racket_weekdays:
        for time in racket_weekday_times:
            db.session.add(SlotCapacity(sport='Tennis', day=day, time=time, max_capacity=capacities['Tennis']))
    
    for day in racket_weekend:
        for time in racket_weekend_times:
            db.session.add(SlotCapacity(sport='Tennis', day=day, time=time, max_capacity=capacities['Tennis']))
    
    # Commit the changes
    db.session.commit()

# Format date for template
def format_date_for_template(date_obj):
    return date_obj.strftime('%Y-%m-%d')

# Function to get day name from date
def get_day_name(date_str):
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    return date_obj.strftime('%A')  # Gets full day name (Monday, Tuesday, etc.)

# Function to convert time from UI format to DB format
def convert_time_format_for_db(time_input):
    # Convert "6:00 AM" to "6am"
    if not time_input:
        return ""
    
    time_parts = time_input.replace(':', ' ').split()
    if len(time_parts) >= 2:
        hour = time_parts[0]
        am_pm = time_parts[-1].lower()
        return f"{hour}{am_pm}"
    return time_input  # Return original if parsing fails

# Function to convert time from DB format to UI format
def convert_time_format_for_ui(time_db):
    # Convert "6am" to "6:00 AM"
    if not time_db:
        return ""
    
    am_pm = time_db[-2:].upper()
    hour = time_db[:-2]
    return f"{hour}:00 {am_pm}"

# Function to check slot availability
def get_slot_availability(sport, day, time):
    # Convert time if needed to match database format
    if ":" in time:
        time = convert_time_format_for_db(time)
    
    # Get the max capacity for this slot
    slot = SlotCapacity.query.filter_by(sport=sport, day=day, time=time).first()
    
    if not slot:
        print(f"DEBUG: No slot found for {sport}, {day}, {time}")
        return 0  # If slot doesn't exist, no availability
    
    # Count existing bookings for this slot
    slot_time = f"{day} {time}"
    bookings_count = Booking.query.filter_by(sport=sport, slot_time=slot_time).count()
    
    # Calculate remaining slots
    remaining = slot.max_capacity - bookings_count
    print(f"DEBUG: Slot {sport}, {day}, {time}: Max={slot.max_capacity}, Booked={bookings_count}, Remaining={remaining}")
    return max(0, remaining)  # Ensure we don't return negative values

# Function to get all slot availabilities for a sport
def get_all_slot_availabilities(sport):
    availabilities = {}
    
    # Get all capacity entries for this sport
    capacities = SlotCapacity.query.filter_by(sport=sport).all()
    
    for capacity in capacities:
        day = capacity.day
        time_db = capacity.time  # This is in "6am" format
        
        # Convert to display format "6:00 AM" for the UI
        display_time = convert_time_format_for_ui(time_db)
        
        slot_time = f"{day} {time_db}"
        
        # Count bookings for this slot
        bookings_count = Booking.query.filter_by(sport=sport, slot_time=slot_time).count()
        
        # Calculate remaining slots
        remaining = capacity.max_capacity - bookings_count
        remaining = max(0, remaining)  # Ensure we don't return negative values
        
        if day not in availabilities:
            availabilities[day] = {}
        
        availabilities[day][display_time] = remaining
    
    return availabilities
def add_column_if_not_exists():
    print("DEBUG: Running add_column_if_not_exists function")
    try:
        with db.engine.connect() as connection:
            # Check if the column already exists
            inspector = inspect(db.engine)
            columns = [col['name'] for col in inspector.get_columns('booking')]
            
            if 'sent_to_controller' not in columns:
                print("DEBUG: Column doesn't exist - adding sent_to_controller column to booking table")
                connection.execute(text('ALTER TABLE booking ADD COLUMN sent_to_controller BOOLEAN DEFAULT FALSE'))
                print("DEBUG: Column added successfully")
            else:
                print("DEBUG: Column sent_to_controller already exists")
    except Exception as e:
        print(f"DEBUG ERROR: Failed to add column - {str(e)}")
# Function to send OTP via Mailtrap
def send_otp_via_email(email, otp):
    try:
        msg = MIMEMultipart()
        msg['From'] = 'from@example.com'
        msg['To'] = email
        msg['Subject'] = 'Your OTP for Login'

        body = f"Your OTP for login is {otp}"
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(MAILTRAP_SMTP_HOST, MAILTRAP_SMTP_PORT)
        server.starttls()
        server.login(MAILTRAP_SMTP_USER, MAILTRAP_SMTP_PASSWORD)

        text = msg.as_string()
        server.sendmail('from@example.com', email, text)
        server.quit()
    except Exception as e:
        print(f"Error: {e}")

# Home page
@app.route('/')
def home():
    return render_template('index.html')

# Admin login route
@app.route('/admin-login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        email = request.form['email']
        if email == ADMIN_EMAIL:
            otp = random.randint(100000, 999999)
            otp_storage[email] = otp
            send_otp_via_email(email, otp)
            return redirect(f'/admin-verify-otp?email={email}')
        else:
            flash('Invalid Admin Email!', 'error')
            return redirect('/admin-login')
    return render_template('admin-login.html')

# Admin OTP verification route
@app.route('/admin-verify-otp', methods=['GET', 'POST'])
def admin_verify_otp():
    email = request.args.get('email')
    if request.method == 'POST':
        entered_otp = int(request.form['otp'])
        if entered_otp == otp_storage.get(email):
            flash('Admin Login Successful!', 'success')
            return redirect('/admin-dashboard')
        else:
            flash('Invalid OTP. Please try again.', 'error')
    return render_template('admin-verify-otp.html', email=email)

# Admin dashboard route
@app.route('/admin-dashboard')
def admin_dashboard():
    # Get all bookings from the database
    bookings = Booking.query.all()
    print(f"DEBUG: Found {len(bookings)} bookings") 
    
    # Get availabilities for each sport
    cricket_availabilities = get_all_slot_availabilities('Cricket')
    badminton_availabilities = get_all_slot_availabilities('Badminton')
    tennis_availabilities = get_all_slot_availabilities('Tennis')
    
    # Get attendance statistics
    total_bookings = len(bookings)
    attended_bookings = Booking.query.filter_by(attended=True).count()
    not_attended_bookings = total_bookings - attended_bookings
    
    # Safe check if sent_to_controller column exists
    sent_to_controller = 0
    if column_exists('booking', 'sent_to_controller'):
        sent_to_controller = Booking.query.filter_by(sent_to_controller=True).count()
    
    return render_template('admin_dashboard.html', 
                          bookings=bookings,
                          cricket_availabilities=cricket_availabilities,
                          badminton_availabilities=badminton_availabilities,
                          tennis_availabilities=tennis_availabilities,
                          total_bookings=total_bookings,
                          attended_bookings=attended_bookings,
                          not_attended_bookings=not_attended_bookings,
                          sent_to_controller=sent_to_controller)

# Route to process admin actions on bookings
@app.route('/process-admin-action', methods=['POST'])
def process_admin_action():
    action = request.form.get('action')
    selected_bookings = request.form.getlist('selected_bookings')
    
    if not selected_bookings:
        flash('No bookings selected', 'error')
        return redirect('/admin-dashboard')
    
    try:
        if action == 'delete':
            for booking_id in selected_bookings:
                booking = Booking.query.get(booking_id)
                if booking:
                    db.session.delete(booking)
            
            flash(f'Successfully deleted {len(selected_bookings)} bookings', 'success')
        
        elif action == 'mark-attended':
            for booking_id in selected_bookings:
                booking = Booking.query.get(booking_id)
                if booking:
                    booking.attended = True
            
            flash(f'Successfully marked {len(selected_bookings)} bookings as attended', 'success')
        
        elif action == 'mark-not-attended':
            for booking_id in selected_bookings:
                booking = Booking.query.get(booking_id)
                if booking:
                    booking.attended = False
            
            flash(f'Successfully marked {len(selected_bookings)} bookings as not attended', 'success')
        
        # Within your process_admin_action function, modify the send-to-controller code:
        elif action == 'send-to-controller':
            # First make sure column exists
            if not column_exists('booking', 'sent_to_controller'):
                print("DEBUG: Creating sent_to_controller column")
                add_column_if_not_exists()
            
            print(f"DEBUG: Processing {len(selected_bookings)} bookings to send to controller")
            successful_bookings = 0
            
            for booking_id in selected_bookings:
                booking = Booking.query.get(booking_id)
                if booking:
                    booking.sent_to_controller = True
                    successful_bookings += 1
                    print(f"DEBUG: Marked booking {booking.id} (ticket: {booking.ticket_id}) as sent_to_controller")
            
            print(f"DEBUG: Successfully marked {successful_bookings} of {len(selected_bookings)} bookings as sent to controller")
            flash(f'Successfully sent {successful_bookings} bookings to controller', 'success')

        db.session.commit()
    except Exception as e:
        db.session.rollback()
        flash(f'Error processing action: {str(e)}', 'error')
    
    return redirect('/admin-dashboard')

# User login route
@app.route('/user-login', methods=['GET', 'POST'])
def user_login():
    if request.method == 'POST':
        email = request.form['email']
        otp = random.randint(100000, 999999)
        otp_storage[email] = otp
        send_otp_via_email(email, otp)
        return redirect(f'/user-verify-otp?email={email}')
    return render_template('user-login.html')

# User OTP verification route
@app.route('/user-verify-otp', methods=['GET', 'POST'])
def user_verify_otp():
    email = request.args.get('email')
    if request.method == 'POST':
        entered_otp = int(request.form['otp'])
        if entered_otp == otp_storage.get(email):
            flash('User Login Successful!', 'success')
            return redirect(f'/user-dashboard?email={email}')
        else:
            flash('Invalid OTP. Please try again.', 'error')
    return render_template('user-verify-otp.html', email=email)

# User dashboard page (after login)
@app.route('/user-dashboard')
def user_dashboard():
    email = request.args.get('email')
    
    # Get current date and max date (7 days from now)
    today = datetime.now().date()
    max_date = today + timedelta(days=7)
    
    # Format dates for template
    today_str = format_date_for_template(today)
    max_date_str = format_date_for_template(max_date)
    
    # Get availabilities for each sport
    cricket_availabilities = get_all_slot_availabilities('Cricket')
    badminton_availabilities = get_all_slot_availabilities('Badminton')
    tennis_availabilities = get_all_slot_availabilities('Tennis')
    
    return render_template('user_dashboard.html', 
                          email=email,
                          today=today_str,
                          max_date=max_date_str,
                          cricket_availabilities=cricket_availabilities,
                          badminton_availabilities=badminton_availabilities,
                          tennis_availabilities=tennis_availabilities)

# API endpoint to get available times for a sport on a specific date
@app.route('/api/get-available-times')
def get_available_times():
    sport = request.args.get('sport')
    date_str = request.args.get('date')
    
    if not sport or not date_str:
        return jsonify({'success': False, 'message': 'Sport and date are required'})
    
    try:
        # Parse the date and get the day name
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        day_name = date_obj.strftime('%A')  # Monday, Tuesday, etc.
        
        # Get all slot capacities for this sport and day
        slots = SlotCapacity.query.filter_by(sport=sport, day=day_name).all()
        
        available_times = []
        for slot in slots:
            # Format the full slot time string
            slot_time = f"{day_name} {slot.time}"
            
            # Count existing bookings for this slot
            bookings_count = Booking.query.filter_by(
                sport=sport, 
                slot_time=slot_time, 
                date=datetime.strptime(date_str, '%Y-%m-%d')
            ).count()
            
            # Calculate available slots
            available = slot.max_capacity - bookings_count
            if available > 0:
                display_time = convert_time_format_for_ui(slot.time)
                available_times.append({
                    'time': slot.time,
                    'display': display_time,
                    'available': available
                })
        
        return jsonify({
            'success': True,
            'times': available_times,
            'day': day_name,
            'date': date_str
        })
    
    except Exception as e:
        print(f"Error fetching available times: {str(e)}")
        return jsonify({'success': False, 'message': str(e)})

# Booking slot route
@app.route('/book-slot', methods=['POST'])
def book_slot():
    if request.method == 'POST':
        email = request.form.get('email')
        sport = request.form.get('sport')
        booking_date = request.form.get('booking_date')  # This is the YYYY-MM-DD date from the form
        time = request.form.get('time')  # This is in '6am' format
        
        if not all([email, sport, booking_date, time]):
            flash('All fields are required', 'error')
            return redirect(f'/user-dashboard?email={email}')
        
        try:
            # Get the day name from the date
            date_obj = datetime.strptime(booking_date, '%Y-%m-%d')
            day = date_obj.strftime('%A')  # Monday, Tuesday, etc.
            
            # Format slot time
            slot_time = f"{day} {time}"
            
            # Check slot availability
            available_slots = get_slot_availability(sport, day, time)
            
            if available_slots <= 0:
                flash(f'No slots available for {sport} on {day} at {convert_time_format_for_ui(time)}', 'error')
                return redirect(f'/user-dashboard?email={email}')
            
            # Check if user already has this booking for this date
            existing_booking = Booking.query.filter_by(
                email=email, 
                sport=sport, 
                slot_time=slot_time,
                date=date_obj
            ).first()
            
            if existing_booking:
                flash(f'You have already booked this slot (Ticket ID: {existing_booking.ticket_id})', 'error')
                return redirect(f'/user-dashboard?email={email}')
                
            # Create the booking ticket
            ticket_id = f"TKT{random.randint(1000, 9999)}"
            
            # Ensure sent_to_controller column exists
            if not column_exists('booking', 'sent_to_controller'):
                add_column_if_not_exists()
            
            new_booking = Booking(
                email=email,
                sport=sport,
                slot_time=slot_time,
                ticket_id=ticket_id,
                date=date_obj,
                attended=False,
                sent_to_controller=False
            )
            
            # Add the booking to the database
            db.session.add(new_booking)
            db.session.commit()
            
            flash(f'Booking Successful! Your Ticket ID is {ticket_id}', 'success')
        
        except Exception as e:
            db.session.rollback()
            flash(f'Booking failed: {str(e)}', 'error')
            print(f"Error during booking: {e}")
        
        return redirect(f'/user-dashboard?email={email}')

# Booking history page
@app.route('/booking-history')
def booking_history():
    email = request.args.get('email')
    bookings = Booking.query.filter_by(email=email).all()
    return render_template('booking_history.html', bookings=bookings)

# Controller login route
@app.route('/controller-login', methods=['GET', 'POST'])
def controller_login():
    if request.method == 'POST':
        email = request.form['email']
        
        # Print to console for debugging
        print(f"Attempting controller login with email: {email}")
        print(f"Allowed controller emails: {ALLOWED_CONTROLLER_EMAILS}")
        
        # Check if the entered email is in the allowed list
        if email in ALLOWED_CONTROLLER_EMAILS:
            try:
                otp = random.randint(100000, 999999)
                otp_storage[email] = otp
                print(f"Generated OTP for {email}: {otp}")
                
                # Send OTP email
                send_otp_via_email(email, otp)
                print(f"OTP email sent to {email}")
                
                flash(f'OTP sent to {email}. Please verify.', 'success')
                return redirect(f'/controller-verify-otp?email={email}')
            except Exception as e:
                print(f"Error sending OTP: {str(e)}")
                flash(f'Error sending OTP: {str(e)}', 'error')
                return redirect('/controller-login')
        else:
            flash(f'Invalid Controller Email! Must be one of: {", ".join(ALLOWED_CONTROLLER_EMAILS)}', 'error')
            return redirect('/controller-login')
    
    return render_template('controller-login.html')

# Controller OTP verification route
@app.route('/controller-verify-otp', methods=['GET', 'POST'])
def controller_verify_otp():
    email = request.args.get('email')  # Get the email from the query parameter
    if email not in ALLOWED_CONTROLLER_EMAILS:
        flash('Invalid controller email!', 'error')
        return redirect('/controller-login')

    if request.method == 'POST':
        # Convert the entered OTP to an integer for correct comparison
        entered_otp = int(request.form['otp'])
        stored_otp = otp_storage.get(email)

        if stored_otp and entered_otp == stored_otp:
            flash('OTP Verified Successfully!', 'success')
            return redirect('/controller-dashboard')
        else:
            flash('Invalid OTP. Please try again.', 'error')
            return redirect(f'/controller-verify-otp?email={email}')

    return render_template('controller-verify-otp.html', email=email)

# Controller dashboard route
# Controller dashboard route
@app.route('/controller-dashboard')
def controller_dashboard():
    # Get the current date
    today = datetime.now().date()
    
    # Debug prints
    print(f"DEBUG: Today's date is {today}")
    
    # Safely check if sent_to_controller column exists before filtering by it
    bookings = []
    if column_exists('booking', 'sent_to_controller'):
        # Get bookings that are sent to controller
        # Temporarily remove date filter to see if that's the issue
        bookings = Booking.query.filter(Booking.sent_to_controller == True).all()
        print(f"DEBUG: Found {len(bookings)} bookings marked as sent_to_controller")
        
        # Log first few bookings for debugging
        for booking in bookings[:5]:
            print(f"DEBUG: Booking ID: {booking.id}, Ticket: {booking.ticket_id}, Date: {booking.date}, Sent to controller: {booking.sent_to_controller}")
    else:
        # If column doesn't exist, just get all bookings for today and past
        bookings = Booking.query.filter(Booking.date <= today).all()
        print(f"DEBUG: Column sent_to_controller doesn't exist, found {len(bookings)} bookings")
        # Add the column for future use
        add_column_if_not_exists()
    
    return render_template('controller_dashboard.html', bookings=bookings, today=today)
# Route to handle attendance marking
@app.route('/manifest.json')
def manifest():
    return jsonify({
        "name": "Attendance Control System",
        "short_name": "ACS",
        "start_url": "/controller-login",
        "display": "standalone",
        "background_color": "#004b91",
        "theme_color": "#004b91",
        "orientation": "portrait",
        "icons": [
            {
                "src": "https://cdn-icons-png.flaticon.com/512/9175/9175234.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    })

@app.route('/service-worker.js')
def service_worker():
    js_content = """
    const CACHE_NAME = 'attendance-v1';
    const urlsToCache = [
      '/',
      '/static/styles.css',
      '/controller-login',
      '/controller-dashboard'
    ];

    self.addEventListener('install', function(event) {
      event.waitUntil(
        caches.open(CACHE_NAME)
          .then(function(cache) {
            return cache.addAll(urlsToCache);
          })
      );
    });

    self.addEventListener('fetch', function(event) {
      event.respondWith(
        caches.match(event.request)
          .then(function(response) {
            return response || fetch(event.request);
          })
      );
    });
    """
    return Response(js_content, mimetype='application/javascript')
@app.route('/mark-attendance', methods=['POST'])
def mark_attendance():
    ticket_id = request.form.get('ticket_id')
    attendance_status = request.form.get('status') == 'true'
    
    try:
        booking = Booking.query.filter_by(ticket_id=ticket_id).first()
        if booking:
            booking.attended = attendance_status
            db.session.commit()
            return jsonify({"success": True, "message": f"Attendance marked as {'attended' if attendance_status else 'not attended'}"})
        else:
            return jsonify({"success": False, "message": "Booking not found"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)})

# API endpoint to search for tickets
@app.route('/api/search-ticket', methods=['GET'])
def search_ticket():
    query = request.args.get('query', '')
    
    if not query:
        return jsonify({"success": False, "message": "No search query provided"})
    
    # Search for the ticket
    booking = Booking.query.filter_by(ticket_id=query).first()
    
    if booking:
        # Format the booking data for response
        booking_data = {
            "id": booking.id,
            "ticket_id": booking.ticket_id,
            "email": booking.email,
            "slot_time": booking.slot_time,
            "sport": booking.sport,
            "attended": booking.attended
        }
        
        # Only add sent_to_controller if column exists
        if column_exists('booking', 'sent_to_controller'):
            booking_data["sent_to_controller"] = booking.sent_to_controller
        
        return jsonify({"success": True, "booking": booking_data})
    else:
        return jsonify({"success": False, "message": "No booking found with this ticket ID"})

# Template filter to format datetime
@app.template_filter('datetime')
def format_datetime(value, format='%Y-%m-%d'):
    if isinstance(value, str):
        try:
            date_obj = datetime.strptime(value, '%Y-%m-%d')
            return date_obj.strftime(format)
        except ValueError:
            return value
    return value.strftime(format) if value else ''

# Initialize the database and run migrations
with app.app_context():
    # Create tables if they don't exist
    # db.drop_all()
    db.create_all()
    add_column_if_not_exists()
    initialize_slot_capacities()

if __name__ == '__main__':
    app.run(debug=True)