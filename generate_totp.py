import pyotp
import qrcode
import os
from pathlib import Path

def generate_totp_setup():
    # Generate a random base32 secret
    secret = pyotp.random_base32()
    
    # Create the TOTP object
    totp = pyotp.totp.TOTP(secret)
    
    # Provisioning URI for authenticator apps
    # Use a descriptive name for the account
    provisioning_uri = totp.provisioning_uri(
        name="TaranveerTrading",
        issuer_name="TradingDashboard"
    )
    
    print("\n" + "="*50)
    print("TOTP GENERATOR & SETUP")
    print("="*50)
    print(f"\nYour TOTP Secret: {secret}")
    print("\nAdd this line to your .env file:")
    print(f"TOTP_SECRET={secret}")
    
    # Generate QR Code
    img = qrcode.make(provisioning_uri)
    qr_filename = "totp_qr.png"
    img.save(qr_filename)
    # Also print an ASCII representation of the QR code for terminal preview
    try:
        qr_ascii = qrcode.QRCode()
        qr_ascii.add_data(provisioning_uri)
        qr_ascii.print_ascii(invert=True)
    except Exception as e:
        print(f"Failed to print ASCII QR: {e}")
    
    print(f"\nQR Code saved to: {os.path.abspath(qr_filename)}")
    print("Scan this QR code with Google Authenticator, Authy, or any TOTP app.")
    print("="*50 + "\n")

if __name__ == "__main__":
    generate_totp_setup()
