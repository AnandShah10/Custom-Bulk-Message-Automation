# CBMS Pro - User Manual

Welcome to the comprehensive guide for using CBMS Pro. This manual covers how to format your Excel files, connect your WhatsApp session, manage your profile, and launch campaigns.

## 1. Setting up your Environment

### The `.env` File
You can set up a default configuration so that the system works seamlessly for all users.
1. Locate the file named `.env` in the main folder.
2. Open it in a text editor (like Notepad).
3. Ensure it contains the following keys:
   - `WASENDER_PERSONAL_TOKEN`: Required for managing dynamic sessions.
   - `WASENDER_API_KEY`: Default fallback key for messaging.
   - `JWT_SECRET_KEY`: Secure string for session management.
   - `BASE_URL`: The URL where your app is hosted (e.g., `http://localhost:8000`).

## 2. WhatsApp Session Management

CBMS Pro allows you to connect your own WhatsApp number to send messages.

1. Click on your user icon in the top-right corner.
2. Select **WhatsApp Session**.
3. Enter your phone number (with country code) and click **Connect WhatsApp**.
4. Scan the generated QR code with your WhatsApp mobile app (Linked Devices).
5. Once "Connected" appears, the system will automatically use your session to send messages.

## 3. User Profile & Security

Customize your account and secure it with modern tools.

### Profile Customization
- Go to **Security Settings** from the user menu.
- Update your **Full Name** to personalize your dashboard experience.
- Your unique **Public ID (UUID)** is displayed here for reference.

### Two-Factor Authentication (MFA)
- In **Security Settings**, click "Set up MFA Now".
- Scan the QR code with an authenticator app (Authy, Google Authenticator).
- Enter the 6-digit code to enable MFA. You will be prompted for this code on every login.

## 4. Formatting your Excel File

The application expects an Excel file (`.xlsx`) containing the contacts you want to message, along with any personalized data variables.

### Mandatory Column
- Your Excel file **MUST** contain a column explicitly headered as `Phone`.
- Numbers should generally be stored in international format without the `+` sign (e.g., `919876543210`). The application automatically cleans `.0` appended by Excel.

### Personalization (Optional)
- You can add custom headers to your columns, such as `Name`, `Company`, `OrderNumber`, etc.
- In your message text area, you can insert `{Name}` or `{Company}`. The generator will replace these tags with the exact row value inside the Excel sheet.

**Example Excel Sheet:**
| Phone        | Name     | Company |
| ------------ | -------- | ------- |
| 919876543210 | John Doe | Acme Co |
| 12025550172  | Jane     | Globex  |

## 3. Navigating the Dashboard

Open your web browser and navigate to the application (typically `http://localhost:8000`).

### Step 1: Selecting Message Types
The left sidebar lists the 6 available WhatsApp message types. You can click on **multiple types** simultaneously! The dashboard will turn blue indicating they are active.

- If you select *both* **Image** and **Text Message**, the system will beam out the image, followed quickly by the text message, to each contact on your list.

### Step 2: Providing Campaign Details
Based on the buttons you highlighted, the right-hand panel dynamically asks for the needed pieces of information:

- **Recipients List:** Always required. Drag and drop your Excel file here.
- **Media / Document URL:** Enter a direct, publicly hosted web link to your media. E.g., `https://example.com/logo.png`. Required for Images, Videos, and Documents.
- **Document Name:** Give your document file a title, e.g., `Monthly_Report.pdf`.
- **Location Fields:** Input the necessary `Latitude` and `Longitude`.
- **Message Content / Caption:** Provide your text structure here.
  - Remember to use the `{ColumnName}` variables here to personalize the messages from the Excel document.

### Step 3: Launch Broadcast
Click the **Launch Broadcast** button.
1. The button will disable itself and switch to "Processing...".
2. If successful, a green "Campaign Launched!" banner surfaces, informing you exactly how many items were pushed to the background queue.
3. The dashboard resets, allowing you to quickly fire off another set if desired.

## 4. Background Processing

Once you see the green success banner, you are free to close the browser. The system processes the rows internally.

### Network Behaviors
- The system places a deliberate, micro pause between successful hits to respect the WaSender API.
- If a contact fails because it hit the rate limit (`HTTP 429`), the system automatically pauses and implements exponential backoff before cleanly retrying.
- Check your local terminal/command prompt window if you wish to monitor real-time "Success" checks natively.
