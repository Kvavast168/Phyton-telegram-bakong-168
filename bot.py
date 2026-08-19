import asyncio
import os
import time
import uuid
from decimal import Decimal, InvalidOperation

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
# CONFIG
# =========================================================

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
BAKONG_TOKEN = os.environ["BAKONG_TOKEN"]
ACCOUNT_ID = os.environ["ACCOUNT_ID"]

MERCHANT_NAME = os.getenv(
    "MERCHANT_NAME",
    "My Store"
)

MERCHANT_CITY = os.getenv(
    "MERCHANT_CITY",
    "Phnom Penh"
)


# =========================================================
# BAKONG
# =========================================================

khqr = KHQR(BAKONG_TOKEN)


# =========================================================
# /start
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data.clear()

    await update.message.reply_text(
        "🤖 Welcome to My Payment Bot!\n\n"
        "💳 Use /pay to create a Bakong payment.\n\n"
        "Commands:\n"
        "/pay - Create payment\n"
        "/cancel - Cancel payment\n"
        "/test - Test Telegram"
    )


# =========================================================
# /pay
# =========================================================

async def pay(update: Update, context: ContextTypes.DEFAULT_TYPE):

    context.user_data["waiting_amount"] = True

    await update.message.reply_text(
        "💰 Enter the amount in USD.\n\n"
        "Examples:\n"
        "1\n"
        "1.99\n"
        "2.50\n"
        "10\n\n"
        "Send /cancel to cancel."
    )


# =========================================================
# /cancel
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
    # Convert amount safely
    # -----------------------------------------------------

    try:

        amount = Decimal(text)

    except InvalidOperation:

        await update.message.reply_text(
            "❌ Invalid amount.\n\n"
            "Example: 1.99"
        )

        return

    # -----------------------------------------------------
    # Validate
    # -----------------------------------------------------

    if amount <= 0:

        await update.message.reply_text(
            "❌ Amount must be greater than $0."
        )

        return

    if amount > Decimal("10000"):

        await update.message.reply_text(
            "❌ Maximum amount is $10,000."
        )

        return

    amount = amount.quantize(
        Decimal("0.01")
    )

    context.user_data["waiting_amount"] = False

    # -----------------------------------------------------
    # Order ID
    # -----------------------------------------------------

    bill_number = (
        "ORDER-"
        + uuid.uuid4().hex[:8].upper()
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
        "⏳ Creating KHQR...\n\n"
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

            amount=float(amount),

            currency="USD",

            store_label=MERCHANT_NAME,

            bill_number=bill_number,

            static=False,

            expiration=1
        )

        print("✅ KHQR CREATED")
        print("QR length:", len(qr_string))


    except Exception as e:

        print(
            "❌ CREATE QR ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Failed to create KHQR.\n\n"
            f"{type(e).__name__}: {e}"
        )

        return


    # =====================================================
    # MD5
    # =====================================================

    try:

        md5 = khqr.generate_md5(
            qr_string
        )

        print(
            "✅ MD5:",
            md5
        )


    except Exception as e:

        print(
            "❌ MD5 ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ Failed to generate payment ID."
        )

        return


    # =====================================================
    # QR IMAGE
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
            f"{type(e).__name__}: {e}"
        )

        return


    # =====================================================
    # OPTIMIZE IMAGE
    # =====================================================

    try:

        image = Image.open(qr_path)

        image.thumbnail(
            (800, 800),
            Image.Resampling.LANCZOS
        )

        image.save(
            qr_path,
            optimize=True
        )

    except Exception as e:

        print(
            "⚠️ Image optimization failed:",
            repr(e)
        )


    # =====================================================
    # SEND QR
    # =====================================================

    try:

        print(
            "📤 Sending QR to Telegram..."
        )

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
                    "📱 Scan this KHQR with "
                    "your banking app.\n\n"
                    "⏳ Waiting for payment..."
                ),

                read_timeout=120,
                write_timeout=120,
                connect_timeout=60,
                pool_timeout=60
            )

        print(
            "✅ QR SENT"
        )


    except Exception as e:

        print(
            "❌ TELEGRAM SEND ERROR:",
            repr(e)
        )

        await update.message.reply_text(
            "❌ KHQR was created, but "
            "Telegram could not send the image.\n\n"
            f"{type(e).__name__}: {e}"
        )

        return


    # =====================================================
    # PAYMENT CHECKER
    # =====================================================

    asyncio.create_task(
        check_payment(
            update,
            md5,
            bill_number,
            amount,
            qr_path
        )
    )


# =========================================================
# PAYMENT CHECKER
# =========================================================

async def check_payment(
    update,
    md5,
    bill_number,
    amount,
    qr_path
):

    start_time = time.time()

    timeout = 10 * 60

    while True:

        try:

            result = khqr.check_payment(
                md5,
                start_time=start_time
            )

            if isinstance(result, tuple):

                status = result[0]
                delay = result[1]

            else:

                status = result
                delay = 5


            print(
                f"[{bill_number}] "
                f"Status: {status}"
            )


            # ------------------------------------------------
            # PAID
            # ------------------------------------------------

            if status == "PAID":

                await update.message.reply_text(

                    "✅ PAYMENT SUCCESSFUL!\n\n"
                    f"💰 Amount: ${amount:.2f} USD\n"
                    f"🧾 Order: {bill_number}\n\n"
                    "🎉 Thank you!"
                )

                try:

                    if os.path.exists(qr_path):
                        os.remove(qr_path)

                except Exception:
                    pass

                return


            # ------------------------------------------------
            # EXPIRED
            # ------------------------------------------------

            if time.time() - start_time >= timeout:

                await update.message.reply_text(

                    "⏰ PAYMENT EXPIRED\n\n"
                    f"💰 Amount: ${amount:.2f} USD\n"
                    f"🧾 Order: {bill_number}\n\n"
                    "Please use /pay again."
                )

                try:

                    if os.path.exists(qr_path):
                        os.remove(qr_path)

                except Exception:
                    pass

                return


            await asyncio.sleep(
                max(3, delay)
            )


        except Exception as e:

            print(
                "❌ PAYMENT CHECK ERROR:",
                repr(e)
            )

            await asyncio.sleep(10)


# =========================================================
# /test
# =========================================================

async def test(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "✅ Telegram connection is working!"
    )


# =========================================================
# ERROR HANDLER
# =========================================================

async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE
):

    print(
        "❌ BOT ERROR:",
        repr(context.error)
    )


# =========================================================
# MAIN
# =========================================================

def main():

    request = HTTPXRequest(

        connect_timeout=60,
        read_timeout=60,
        write_timeout=120,
        pool_timeout=60,
        connection_pool_size=8
    )

    updates_request = HTTPXRequest(

        connect_timeout=60,
        read_timeout=60,
        write_timeout=120,
        pool_timeout=60,
        connection_pool_size=8
    )


    app = (
        Application.builder()

        .token(
            TELEGRAM_TOKEN
        )

        .request(
            request
        )

        .get_updates_request(
            updates_request
        )

        .build()
    )


    # -----------------------------------------------------
    # Commands
    # -----------------------------------------------------

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


    # -----------------------------------------------------
    # Amount input
    # -----------------------------------------------------

    app.add_handler(

        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            receive_amount
        )
    )


    # -----------------------------------------------------
    # Error handler
    # -----------------------------------------------------

    app.add_error_handler(
        error_handler
    )


    # -----------------------------------------------------
    # Start
    # -----------------------------------------------------

    print()
    print("==============================")
    print("🤖 BAKONG TELEGRAM BOT")
    print("==============================")
    print("🚀 BOT IS RUNNING")
    print("==============================")
    print()


    app.run_polling(
        drop_pending_updates=True
    )


# =========================================================
# RUN
# =========================================================

if __name__ == "__main__":
    main()
