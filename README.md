# Smart Sports Complex Reservation System 🏸📧

This is a **multi-role web application** for managing a sports complex. It features **OTP-based login**, real-time **slot booking**, **ticket verification**, and **admin monitoring** — all integrated with **Mailtrap.io** for email testing.

---

## 👥 Roles in the System

### 1. 👤 User
- Registers/logs in using **OTP sent to their email** via Mailtrap
- Can **view available timeslots** for sports like Badminton, Cricket, Kabaddi, and Tennis
- Books a slot and gets a **unique ticket number**
- That ticket is later verified by the controller

### 2. 🛠️ Admin
- Logs in via OTP (**only one fixed email allowed** — hardcoded for security)
- Views **all bookings made by users**
- Sends booking data to **Controller** after reviewing
- Gets real-time **attendance updates** from the Controller

### 3. ✅ Controller
- OTP login for **only 3 pre-approved emails** (configured)
- Receives booking info from Admin
- When player shows up, they enter their **ticket number**
- Marks the player as **Attended / Not Attended**
- This status is reflected live in the **Admin dashboard**

---

## 📩 OTP via Email

- All OTPs are sent using **Mailtrap.io**
- Only you (developer) get OTPs, since Mailtrap **catches emails for testing**
- Other fake emails (not yours) won't receive OTPs unless they are in your Mailtrap inbox setup

---

## 🛠️ Technologies Used

- **Frontend**: HTML, CSS, JavaScript
- **Backend**: Python (Flask)
- **Database**: SQLite
- **Email Service**: Mailtrap.io (SMTP)

---

## 🔧 Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/smart-sports-complex
cd smart-sports-complex
