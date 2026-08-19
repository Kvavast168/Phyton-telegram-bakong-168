import asyncio
import os
import time
import uuid

from PIL import Image

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from telegram.request import HTTPXRequest

from bakong_khqr import KHQR


# =========================================================
# CONFIGURATION
# =========================================================

TELEGRAM_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

BAKONG_TOKEN = "YOUR_BAKONG_DEVELOPER_TOKEN"

ACCOUNT_ID = "YOUR_BAKONG_ACCOUNT_ID"

MERCHANT_NAME = "My Store"

MERCHANT_CITY = "Phnom Penh"


# =========================================================
# BAKONG CLIENT
# =========================================================

khqr = KHQR(BAKONG_TOKEN)


# =========================================================
# /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "🤖 Welcome to My Payment Bot!\n\n"
        "💰 Use /pay to create a Bakong payment.\n\n"
        "Example:\n"
        "/pay"
    )


# =========================================================
# /PAY
# =========================================================

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["waiting_amount"] = True

    await update.message.reply_text(
        "💰 Enter the amount you want to pay.\n\n"
        "Currency: USD\n\n"
        "Examples:\n"
        "1\n"
        "1.99\n"
        "2.50\n"
        "10\n\n"
        "Send /cancel to cancel."
    )


# =========================================================
# /CANCEL
# =========================================================

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["waiting_amount"] = False

    await update.message.reply_text(
        "❌ Payment cancelled."
    )


# =========================================================
# RECEIVE AMOUNT
# =========================================================

async def receive_amount(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.user_data.get("waiting_amount"):
        return

    text = update.message.text.strip()

    # -----------------------------------------------------
    # Convert amount
    # -----------------------------------------------------

    try:

        amount = float(text)

    except ValueError:

        await update.message.reply_text(
            "❌ Invalid amount.\n\n"
            "Please enter a number.\n\n"
            "Example:\n"
            "2.50"
        )

        return

    # -----------------------------------------------------
    # Validate amount
    # -----------------------------------------------------

    if amount <= 0:

        await update.message.reply_text(
            "❌ Amount must be greater than $0."
        )

        return

    if amount > 10000:

        await update.message.reply_text(
            "❌ Maximum amount is $10,000 USD."
        )

        return

    amount = round(amount, 2)

    # Stop waiting
    context.user_data["waiting_amount"] = False

    # -----------------------------------------------------
    # Create unique order
    # -----------------------------------------------------

    bill_number = (
        "ORDER-" +
        uuid.uuid4().hex[:8].upper()
    )

    print()
    print("==============================")
    print("CREATING KHQR")
    print("==============================")
    print("Account:", ACCOUNT_ID)
    print("Amount:", amount)
    print("Currency: USD")
    print("Bill:", bill_number)
    print("==============================")


    await update.message.reply_text(
        f"⏳ Creating payment...\n\n"
        f"💰 Amount: ${amount:.2f} USD"
    )


    # =====================================================
    # CREATE KHQR
    # =====================================================

    try:

        qr_string = khqr.create_qr(

            account_id=ACCOUNT_ID,

            merchant_name=MERCHANT_NAME,

            merchant_city=MERCHANT_CITY,

            amount=amount,

            currency="USD",

            store_label=MERCHANT_NAME,

            bill_number=bill_number,

            static=False,

            expiration=1
        )

        print("✅ KHQR CREATED")
        print("QR length:", len(qr_string))


    except Exception as e:

        print()
        print("❌ CREATE QR ERROR")
        print("Type:", type(e).__name__)
        print("Error:", str(e))

        await update.message.reply_text(
            "❌ Failed to create KHQR.\n\n"
            f"Error type: {type(e).__name__}\n"
            f"Error: {str(e)}"
        )

        return


    # =====================================================
    # GENERATE MD5
    # =====================================================

    try:

        md5 = khqr.generate_md5(
            qr_string
        )

        print("✅ MD5:", md5)


    except Exception as e:

        print(
            "❌ MD5 ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Failed to generate payment ID.\n\n"
            f"{e}"
        )

        return


    # =====================================================
    # CREATE QR IMAGE
    # =====================================================

    qr_filename = (
        f"{bill_number}.png"
    )

    try:

        qr_path = khqr.qr_image(

            qr_string,

            output_path=qr_filename
        )

        print(
            "✅ QR IMAGE:",
            qr_path
        )


    except Exception as e:

        print(
            "❌ QR IMAGE ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Failed to create QR image.\n\n"
            f"{e}"
        )

        return


    # =====================================================
    # RESIZE QR IMAGE
    # =====================================================

    try:

        image = Image.open(qr_path)

        # Make QR reasonably small
        image.thumbnail(
            (700, 700),
            Image.Resampling.LANCZOS
        )

        image.save(
            qr_path,
            optimize=True
        )

        print("✅ QR IMAGE OPTIMIZED")

    except Exception as e:

        print(
            "⚠️ IMAGE OPTIMIZATION ERROR:",
            repr(e)
        )

        # Continue anyway


    # =====================================================
    # SEND QR TO TELEGRAM
    # =====================================================

    try:

        print("📤 Sending QR to Telegram...")

        with open(
            qr_path,
            "rb"
        ) as photo:

            await update.message.reply_photo(

                photo=photo,

                caption=(
                    "💳 BAKONG PAYMENT\n\n"

                    f"💰 Amount: ${amount:.2f} USD\n"

                    f"🧾 Order: {bill_number}\n\n"

                    "📱 Scan this KHQR "
                    "with your banking app.\n\n"

                    "⏳ Waiting for payment..."
                ),

                # Longer upload timeout
                read_timeout=120,

                write_timeout=120,

                connect_timeout=60,

                pool_timeout=60
            )

        print("✅ QR SENT TO TELEGRAM")


    except Exception as e:

        print()
        print("❌ TELEGRAM SEND ERROR")
        print("Type:", type(e).__name__)
        print("Error:", str(e))

        await update.message.reply_text(
            "❌ KHQR was created successfully, "
            "but Telegram couldn't upload the QR image.\n\n"
            f"Error: {e}"
        )

        return


    # =====================================================
    # START PAYMENT CHECKER
    # =====================================================

    asyncio.create_task(

        check_payment(

            update=update,

            md5=md5,

            bill_number=bill_number,

            amount=amount,

            qr_path=qr_path
        )
    )


# =========================================================
# CHECK PAYMENT
# =========================================================

async def check_payment(
    update,
    md5,
    bill_number,
    amount,
    qr_path
):

    start_time = time.time()

    # Payment expires after 10 minutes
    timeout = 10 * 60


    while True:

        try:

            result = khqr.check_payment(

                md5,

                start_time=start_time
            )


            # ------------------------------------------------
            # Handle SDK result
            # ------------------------------------------------

            if isinstance(result, tuple):

                status = result[0]

                delay = result[1]

            else:

                status = result

                delay = 5


            print(
                f"[{bill_number}] "
                f"Payment status: {status}"
            )


            # =================================================
            # PAID
            # =================================================

            if status == "PAID":

                print(
                    f"✅ PAYMENT RECEIVED: "
                    f"{bill_number}"
                )

                await update.message.reply_text(

                    "✅ PAYMENT SUCCESSFUL!\n\n"

                    f"💰 Amount: ${amount:.2f} USD\n"

                    f"🧾 Order: {bill_number}\n\n"

                    "🎉 Thank you!"
                )

                # Delete QR file
                try:

                    if os.path.exists(qr_path):

                        os.remove(qr_path)

                except Exception:
                    pass

                return


            # =================================================
            # TIMEOUT
            # =================================================

            elapsed = (
                time.time() -
                start_time
            )


            if elapsed >= timeout:

                print(
                    f"⏰ PAYMENT EXPIRED: "
                    f"{bill_number}"
                )

                await update.message.reply_text(

                    "⏰ PAYMENT EXPIRED\n\n"

                    f"💰 Amount: ${amount:.2f} USD\n"

                    f"🧾 Order: {bill_number}\n\n"

                    "Please use /pay to create "
                    "a new payment."
                )

                return


            # ------------------------------------------------
            # Wait before checking again
            # ------------------------------------------------

            await asyncio.sleep(
                max(3, delay)
            )


        except Exception as e:

            print(
                "❌ PAYMENT CHECK ERROR:",
                repr(e)
            )

            # Don't stop immediately.
            # Try again after 10 seconds.

            await asyncio.sleep(10)


# =========================================================
# TEST TELEGRAM CONNECTION
# =========================================================

async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "✅ Telegram connection is working!"
    )


# =========================================================
# MAIN
# =========================================================

def main():

    # =====================================================
    # NORMAL TELEGRAM REQUEST
    # =====================================================

    request = HTTPXRequest(

        connect_timeout=60,

        read_timeout=60,

        write_timeout=120,

        pool_timeout=60,

        connection_pool_size=8
    )


    # =====================================================
    # LONG POLLING REQUEST
    # =====================================================

    updates_request = HTTPXRequest(

        connect_timeout=60,

        read_timeout=60,

        write_timeout=120,

        pool_timeout=60,

        connection_pool_size=8
    )


    # =====================================================
    # CREATE APPLICATION
    # =====================================================

    app = (

        Application.builder()

        .token(TELEGRAM_TOKEN)

        .request(request)

        .get_updates_request(
            updates_request
        )

        .build()
    )


    # =====================================================
    # COMMANDS
    # =====================================================

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "pay",
            pay
        )
    )

    app.add_handler(
        CommandHandler(
            "cancel",
            cancel
        )
    )

    app.add_handler(
        CommandHandler(
            "test",
            test
        )
    )


    # =====================================================
    # TEXT INPUT
    # =====================================================

    app.add_handler(

        MessageHandler(

            filters.TEXT &
            ~filters.COMMAND,

            receive_amount
        )
    )


    # =====================================================
    # START
    # =====================================================

    print()
    print("==============================")
    print("🤖 BOT IS RUNNING")
    print("==============================")
    print()


    app.run_polling(

        drop_pending_updates=True
    )


# =========================================================
# RUN PROGRAM
# =========================================================

if __name__ == "__main__":

    main()