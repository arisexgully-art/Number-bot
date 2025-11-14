import asyncio
import logging
import os
import threading  # <-- থ্রেডিং আবার যোগ করা হয়েছে
from flask import Flask  # <-- Flask আবার যোগ করা হয়েছে
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.filters.callback_data import CallbackData
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Document
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from typing import Dict, List, Optional

# --- Environment Variables থেকে টোকেন লোড করা ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID_STR = os.environ.get("ADMIN_ID")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME")
# --- ⚠️ নতুন: Render-এর দেওয়া PORT লোড করা ---
RENDER_PORT = int(os.environ.get('PORT', 10000)) # ডিফল্ট 10000

# চেক করা হচ্ছে
if not BOT_TOKEN or not ADMIN_ID_STR or not ADMIN_USERNAME:
    logging.critical("CRITICAL ERROR: BOT_TOKEN, ADMIN_ID, or ADMIN_USERNAME is not set!")
    exit()

try:
    ADMIN_ID = int(ADMIN_ID_STR)
except ValueError:
    logging.critical("CRITICAL ERROR: ADMIN_ID is not a valid integer!")
    exit()
# -----------------------------------------------------------------

# --- ইন-মেমরি ডাটাবেস ---
mock_db: Dict = {
    "services": {},
    "settings": {
        "num_limit": 7
    }
}

# --- FSM স্টেটস (States) ---
class AdminStates(StatesGroup):
    add_service_name = State()
    add_country_select_service = State()
    add_country_name = State()
    add_number_select_service = State()
    add_number_select_country = State()
    add_number_method_choice = State()  
    add_number_input_text = State()     
    add_number_input_file = State()     
    remove_service_select = State()
    remove_country_select_service = State()
    remove_country_select = State()
    set_num_limit = State()

class UserStates(StatesGroup):
    get_number_select_service = State()
    get_number_select_country = State()
    get_number_display = State()

# --- কলব্যাক ডেটা ফ্যাক্টরি ---
class ServiceCallback(CallbackData, prefix="svc"):
    action: str  
    service_name: str
class CountryCallback(CallbackData, prefix="ctry"):
    action: str  
    service_name: str
    country_name: str
class NavCallback(CallbackData, prefix="nav"):
    action: str 
    current_state: Optional[str] = None

# --- বট এবং ডিসপ্যাচার সেটআপ ---
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# --- রিপ্লাই কীবোর্ড (প্রধান মেনু) ---
# ... (আপনার কীবোর্ডের কোড এখানে থাকবে, কোনো পরিবর্তন নেই) ...
admin_buttons = [
    [KeyboardButton(text="➕ Add Number"), KeyboardButton(text="⚙️ Add Service")],
    [KeyboardButton(text="🗑️ Remove Service"), KeyboardButton(text="🌍 Add country")],
    [KeyboardButton(text="❌ Remove country"), KeyboardButton(text="Num Limit")],
    [KeyboardButton(text="🔢 Get Number"), KeyboardButton(text="🆘 Support")],
    [KeyboardButton(text="🔙 Cancel Operation")]
]
admin_keyboard = ReplyKeyboardMarkup(keyboard=admin_buttons, resize_keyboard=True, input_field_placeholder="Select an option...")
user_buttons = [
    [KeyboardButton(text="🔢 Get Number"), KeyboardButton(text="🆘 Support")],
    [KeyboardButton(text="🔙 Cancel Operation")]
]
user_keyboard = ReplyKeyboardMarkup(keyboard=user_buttons, resize_keyboard=True, input_field_placeholder="Select an option...")


# --- Helper Function: সার্ভিস কীবোর্ড ---
def get_services_keyboard(action_prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    services = mock_db["services"].keys()
    if not services:
        builder.row(InlineKeyboardButton(text="🚫 কোনো সার্ভিস পাওয়া যায়নি", callback_data="none"))
    else:
        for service in services:
            builder.row(InlineKeyboardButton(text=service, callback_data=ServiceCallback(action=action_prefix, service_name=service).pack()))
    builder.row(InlineKeyboardButton(text="🔙 Cancel", callback_data="cancel_fsm"))
    return builder.as_markup()

# --- Helper Function: দেশ কীবোর্ড ---
def get_countries_keyboard(service_name: str, action_prefix: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if service_name not in mock_db["services"]:
        builder.row(InlineKeyboardButton(text="🚫 সার্ভিস খুঁজে পাওয়া যায়নি", callback_data="none"))
        builder.row(InlineKeyboardButton(text="🔙 Back to Services", callback_data=NavCallback(action="back").pack()))
        return builder.as_markup()
    countries = mock_db["services"].get(service_name, {}).keys()
    if not countries:
        builder.row(InlineKeyboardButton(text="🚫 কোনো দেশ পাওয়া যায়নি", callback_data="none"))
    else:
        for country in countries:
            builder.row(InlineKeyboardButton(text=country, callback_data=CountryCallback(action=action_prefix, service_name=service_name, country_name=country).pack()))
    builder.row(InlineKeyboardButton(text="🔙 Back to Services", callback_data=NavCallback(action="back").pack()))
    return builder.as_markup()

# --- প্রধান কমান্ড হ্যান্ডলার (/start) ---
@dp.message(Command("start"))
async def send_welcome(message: Message, state: FSMContext):
    await state.clear() 
    user_id = message.from_user.id
    if user_id == ADMIN_ID:
        await message.answer(f"স্বাগতম, অ্যাডমিন {message.from_user.first_name}!", reply_markup=admin_keyboard)
    else:
        await message.answer(f"স্বাগতম, {message.from_user.first_name}!", reply_markup=user_keyboard)

# --- FSM ক্যানসেল হ্যান্ডলার ---
@dp.callback_query(F.data == "cancel_fsm")
async def cancel_fsm_handler(query: CallbackQuery, state: FSMContext):
    await state.clear(); await query.message.edit_text("অপারেশন বাতিল করা হয়েছে।"); await query.answer()
@dp.message(F.text == "🔙 Cancel Operation", StateFilter("*"))
async def handle_cancel_operation(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("আপনি বর্তমানে কোনো অপারেশনে নেই।"); return
    await state.clear(); await message.answer("অপারেশন বাতিল করা হয়েছে। প্রধান মেনুতে ফিরে আসা হলো।")

# --- (বাকি সব অ্যাডমিন এবং ইউজার হ্যান্ডলার এখানে থাকবে...) ---
# --- ১. ADMIN: Add Service ---
@dp.message(F.text == "⚙️ Add Service", StateFilter(None))
async def admin_add_service_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.add_service_name)
    await message.answer("নতুন সার্ভিসের নাম লিখুন (যেমন: WhatsApp, Telegram):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Cancel", callback_data="cancel_fsm")]]))
@dp.message(AdminStates.add_service_name, F.text)
async def admin_add_service_name_input(message: Message, state: FSMContext):
    service_name = message.text.strip()
    if service_name in mock_db["services"]:
        await message.answer(f"'{service_name}' নামে সার্ভিস আগে থেকেই আছে। অন্য নাম দিন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Cancel", callback_data="cancel_fsm")]]))
    else:
        mock_db["services"][service_name] = {}; await state.clear(); await message.answer(f"✅ সার্ভিস '{service_name}' সফলভাবে যোগ করা হয়েছে।"); logging.info(f"Admin added service: {service_name}.")

# --- ২. ADMIN: Add Country ---
@dp.message(F.text == "🌍 Add country", StateFilter(None))
async def admin_add_country_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.add_country_select_service)
    await message.answer("কোন সার্ভিসের অধীনে দেশ যোগ করতে চান?", reply_markup=get_services_keyboard(action_prefix="select_for_add_country"))
@dp.callback_query(ServiceCallback.filter(F.action == "select_for_add_country"), AdminStates.add_country_select_service)
async def admin_add_country_service_selected(query: CallbackQuery, callback_data: ServiceCallback, state: FSMContext):
    service_name = callback_data.service_name; await state.update_data(service_name=service_name); await state.set_state(AdminStates.add_country_name)
    await query.message.edit_text(f"<b>সার্ভিস: {service_name}</b>\n\nএই সার্ভিসে দেশ যোগ করতে, নিচে দেশের নাম টাইপ করে সেন্ড করুন।", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Services", callback_data=NavCallback(action="back").pack())]]))
    await query.answer()
@dp.message(AdminStates.add_country_name, F.text)
async def admin_add_country_name_input(message: Message, state: FSMContext):
    country_name = message.text.strip(); data = await state.get_data(); service_name = data.get("service_name")
    if not service_name or service_name not in mock_db["services"]:
        await state.clear(); await message.answer("কিছু একটা ভুল হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।"); return
    if country_name in mock_db["services"][service_name]:
        await message.answer(f"'{country_name}' দেশটি '{service_name}' সার্ভিসে আগে থেকেই আছে। অন্য নাম দিন:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Services", callback_data=NavCallback(action="back").pack())]]))
    else:
        mock_db["services"][service_name][country_name] = []; await state.clear(); await message.answer(f"✅ দেশ '{country_name}' সফলভাবে '{service_name}' সার্ভিসে যোগ করা হয়েছে।"); logging.info(f"Admin added country: {country_name} to {service_name}.")

# --- ৩. ADMIN: Add Number ---
@dp.message(F.text == "➕ Add Number", StateFilter(None))
async def admin_add_number_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.add_number_select_service)
    await message.answer("কোন সার্ভিসে নম্বর যোগ করতে চান?", reply_markup=get_services_keyboard(action_prefix="select_for_add_num"))
@dp.callback_query(ServiceCallback.filter(F.action == "select_for_add_num"), AdminStates.add_number_select_service)
async def admin_add_number_service_selected(query: CallbackQuery, callback_data: ServiceCallback, state: FSMContext):
    service_name = callback_data.service_name; await state.update_data(service_name=service_name); await state.set_state(AdminStates.add_number_select_country)
    await query.message.edit_text(f"সার্ভিস: {service_name}\n\nকোন দেশে নম্বর যোগ করতে চান?", reply_markup=get_countries_keyboard(service_name, action_prefix="select_for_add_num"))
    await query.answer()
@dp.callback_query(CountryCallback.filter(F.action == "select_for_add_num"), AdminStates.add_number_select_country)
async def admin_add_number_country_selected(query: CallbackQuery, callback_data: CountryCallback, state: FSMContext):
    await state.update_data(service_name=callback_data.service_name, country_name=callback_data.country_name); await state.set_state(AdminStates.add_number_method_choice)
    method_keyboard = InlineKeyboardBuilder(); method_keyboard.row(InlineKeyboardButton(text="✍️ Add via Text", callback_data="add_num:text")); method_keyboard.row(InlineKeyboardButton(text="📄 Add via Text File", callback_data="add_num:file")); method_keyboard.row(InlineKeyboardButton(text="🔙 Back to Countries", callback_data=NavCallback(action="back").pack()))
    await query.message.edit_text(f"<b>সার্ভিস: {callback_data.service_name}</b>\n<b>দেশ: {callback_data.country_name}</b>\n\nআপনি কিভাবে নম্বর যোগ করতে চান? (টেক্সট বা ফাইল)", reply_markup=method_keyboard.as_markup())
    await query.answer()
@dp.callback_query(F.data == "add_num:text", AdminStates.add_number_method_choice)
async def handle_add_num_text_choice(query: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.add_number_input_text); keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Method Choice", callback_data=NavCallback(action="back").pack())]])
    await query.message.edit_text("<b>নির্দেশনা:</b>\nঅনুগ্রহ করে নম্বরগুলি টাইপ করুন। প্রতিটি নম্বর একটি নতুন লাইনে লিখুন:", reply_markup=keyboard); await query.answer()
@dp.callback_query(F.data == "add_num:file", AdminStates.add_number_method_choice)
async def handle_add_num_file_choice(query: CallbackQuery, state: FSMContext):
    await state.set_state(AdminStates.add_number_input_file); keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Back to Method Choice", callback_data=NavCallback(action="back").pack())]])
    await query.message.edit_text("<b>নির্দেশনা:</b>\nঅনুগ্রহ করে একটি <b>.txt</b> ফাইল আপলোড করুন। ফাইলের প্রতিটি নম্বর একটি নতুন লাইনে থাকতে হবে:", reply_markup=keyboard); await query.answer()
async def process_numbers(text_data: str, service_name: str, country_name: str) -> int:
    numbers = [num.strip() for num in text_data.splitlines() if num.strip()]; count = 0
    if country_name not in mock_db["services"][service_name]: mock_db["services"][service_name][country_name] = []
    for num in numbers:
        if num not in mock_db["services"][service_name][country_name]: mock_db["services"][service_name][country_name].append(num); count += 1
    return count
@dp.message(AdminStates.add_number_input_text, F.text)
async def admin_add_number_text_input(message: Message, state: FSMContext):
    data = await state.get_data(); service = data.get("service_name"); country = data.get("country_name")
    if not service or not country or service not in mock_db["services"]: await state.clear(); await message.answer("কিছু একটা ভুল হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।"); return
    count = await process_numbers(message.text, service, country); await state.clear(); await message.answer(f"✅ সফলভাবে {count} টি নতুন নম্বর '{country}' ({service}) তে যোগ করা হয়েছে।"); logging.info(f"Admin added {count} numbers via text.")
@dp.message(AdminStates.add_number_input_file, F.document)
async def admin_add_number_file_input(message: Message, state: FSMContext):
    if not message.document.mime_type == "text/plain": await message.answer("অনুগ্রহ করে একটি .txt ফাইল আপলোড করুন।"); return
    data = await state.get_data(); service = data.get("service_name"); country = data.get("country_name")
    if not service or not country or service not in mock_db["services"]: await state.clear(); await message.answer("কিছু একটা ভুল হয়েছে। অনুগ্রহ করে আবার চেষ্টা করুন।"); return
    try:
        file = await bot.get_file(message.document.file_id); file_content = await bot.download_file(file.file_path); text_data = file_content.read().decode('utf-8')
        count = await process_numbers(text_data, service, country); await state.clear(); await message.answer(f"✅ ফাইল থেকে সফলভাবে {count} টি নতুন নম্বর '{country}' ({service}) তে যোগ করা হয়েছে।"); logging.info(f"Admin added {count} numbers via file.")
    except Exception as e: await message.answer(f"ফাইল প্রসেস করতে সমস্যা হয়েছে: {e}")

# --- ৪. ADMIN: Remove Service ---
@dp.message(F.text == "🗑️ Remove Service", StateFilter(None))
async def admin_remove_service_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.remove_service_select)
    await message.answer("আপনি কোন সার্ভিসটি মুছে ফেলতে চান?", reply_markup=get_services_keyboard(action_prefix="remove_service"))
@dp.callback_query(ServiceCallback.filter(F.action == "remove_service"), AdminStates.remove_service_select)
async def admin_remove_service_selected(query: CallbackQuery, callback_data: ServiceCallback, state: FSMContext):
    service_name = callback_data.service_name
    try: del mock_db["services"][service_name]; await state.clear(); await query.message.edit_text(f"✅ সার্ভিস '{service_name}' সফলভাবে মুছে ফেলা হয়েছে।"); logging.info(f"Admin removed service: {service_name}.")
    except KeyError: await state.clear(); await query.message.edit_text("❌ ত্রুটি: সার্ভিসটি খুঁজে পাওয়া যায়নি।"); await query.answer()

# --- ৫. ADMIN: Remove Country ---
@dp.message(F.text == "❌ Remove country", StateFilter(None))
async def admin_remove_country_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.remove_country_select_service)
    await message.answer("কোন সার্ভিস থেকে দেশ মুছতে চান?", reply_markup=get_services_keyboard(action_prefix="select_for_remove_country"))
@dp.callback_query(ServiceCallback.filter(F.action == "select_for_remove_country"), AdminStates.remove_country_select_service)
async def admin_remove_country_service_selected(query: CallbackQuery, callback_data: ServiceCallback, state: FSMContext):
    service_name = callback_data.service_name; await state.update_data(service_name=service_name); await state.set_state(AdminStates.remove_country_select)
    await query.message.edit_text(f"সার্ভিস: {service_name}\n\nআপনি কোন দেশটি মুছে ফেলতে চান?", reply_markup=get_countries_keyboard(service_name, action_prefix="remove_country")); await query.answer()
@dp.callback_query(CountryCallback.filter(F.action == "remove_country"), AdminStates.remove_country_select)
async def admin_remove_country_selected(query: CallbackQuery, callback_data: CountryCallback, state: FSMContext):
    service_name = callback_data.service_name; country_name = callback_data.country_name
    try: del mock_db["services"][service_name][country_name]; await state.clear(); await query.message.edit_text(f"✅ দেশ '{country_name}' ({service_name}) সফলভাবে মুছে ফেলা হয়েছে।"); logging.info(f"Admin removed country: {country_name} from {service_name}.")
    except KeyError: await state.clear(); await query.message.edit_text("❌ ত্রুটি: দেশটি খুঁজে পাওয়া যায়নি।"); await query.answer()

# --- ৬. ADMIN: Set Num Limit ---
@dp.message(F.text == "Num Limit", StateFilter(None))
async def handle_num_limit_start(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await state.set_state(AdminStates.set_num_limit); current_limit = mock_db["settings"]["num_limit"]
    await message.answer(f"বর্তমান নম্বর লিমিট <b>{current_limit}</b> টি।\nনতুন লিমিট সংখ্যায় লিখুন (যেমন: 5):", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔙 Cancel", callback_data="cancel_fsm")]]))
@dp.message(AdminStates.set_num_limit, F.text)
async def handle_num_limit_input(message: Message, state: FSMContext):
    try:
        new_limit = int(message.text.strip());
        if new_limit <= 0: await message.answer("লিমিট অবশ্যই 0-এর বেশি হতে হবে।"); return
        mock_db["settings"]["num_limit"] = new_limit; await state.clear(); await message.answer(f"✅ নম্বর লিমিট সফলভাবে <b>{new_limit}</b> টি সেট করা হয়েছে।"); logging.info(f"Num limit set to {new_limit}")
    except ValueError: await message.answer("ত্রুটি: অনুগ্রহ করে শুধু সংখ্যা টাইপ করুন।")
    except Exception as e: await message.answer(f"একটি ত্রুটি ঘটেছে: {e}")

# --- ৭. USER/ADMIN: Get Number ---
@dp.message(F.text == "🔢 Get Number", StateFilter(None))
async def user_get_number_start(message: Message, state: FSMContext):
    await state.set_state(UserStates.get_number_select_service)
    await message.answer("আপনি কোন সার্ভিসের জন্য নম্বর চান?", reply_markup=get_services_keyboard(action_prefix="select_for_get"))
@dp.callback_query(ServiceCallback.filter(F.action == "select_for_get"), UserStates.get_number_select_service)
async def user_get_number_service_selected(query: CallbackQuery, callback_data: ServiceCallback, state: FSMContext):
    service_name = callback_data.service_name; await state.update_data(service_name=service_name); await state.set_state(UserStates.get_number_select_country)
    await query.message.edit_text(f"সার্ভিস: {service_name}\n\nকোন দেশের নম্বর চান?", reply_markup=get_countries_keyboard(service_name, action_prefix="select_for_get")); await query.answer()
@dp.callback_query(CountryCallback.filter(F.action == "select_for_get"), UserStates.get_number_select_country)
async def user_get_number_country_selected(query: CallbackQuery, callback_data: CountryCallback, state: FSMContext):
    await state.update_data(service_name=callback_data.service_name, country_name=callback_data.country_name); await state.set_state(UserStates.get_number_display)
    await show_numbers_page(query.message, state, edit=False); await query.answer()
async def show_numbers_page(message: Message, state: FSMContext, edit: bool = True):
    data = await state.get_data(); service = data.get("service_name"); country = data.get("country_name")
    if not service or not country: await state.clear(); await message.answer("কিছু একটা ভুল হয়েছে। /start দিন।"); return
    try:
        per_page = mock_db["settings"]["num_limit"]; all_numbers = mock_db["services"].get(service, {}).get(country, []); numbers_to_show = all_numbers[:per_page]
        text = f"<b>সার্ভিস: {service}</b>\n"
        if not numbers_to_show: text += f"\n<b>দেশ: {country}</b>\n\n🚫 এই দেশের জন্য আর কোনো নম্বর নেই।"
        else:
            text += f"<b>দেশ: {country}</b> ({len(numbers_to_show)} টি নম্বর)\n\n"
            for num in numbers_to_show: text += f"📞 <b>{country} WS Number Assigned:</b>\n<code>{num}</code>\nWaiting for OTP...\n\n"
            mock_db["services"][service][country] = all_numbers[per_page:]; logging.info(f"Gave {len(numbers_to_show)} numbers. {len(mock_db['services'][service][country])} remain.")
        builder = InlineKeyboardBuilder()
        if len(mock_db["services"][service][country]) > 0: builder.row(InlineKeyboardButton(text=f"🔄 Refresh (Get Next {per_page})", callback_data=NavCallback(action="refresh").pack()))
        else:
            if len(numbers_to_show) > 0: builder.row(InlineKeyboardButton(text="🚫 আর নম্বর নেই", callback_data="none"))
            elif len(all_numbers) == 0: builder.row(InlineKeyboardButton(text="🚫 কোনো নম্বর নেই", callback_data="none"))
        builder.row(InlineKeyboardButton(text="🌍 Change Country", callback_data=NavCallback(action="change_country").pack()), InlineKeyboardButton(text="⚙️ Change Service", callback_data=NavCallback(action="change_service").pack()))
        builder.row(InlineKeyboardButton(text="🔙 Back to Main Menu", callback_data="cancel_fsm"))
        if edit:
            try: await message.edit_text(text, reply_markup=builder.as_markup())
            except Exception as e: logging.warning(f"Could not edit message: {e}")
        else:
            try: await message.delete() 
            except Exception: pass 
            await message.answer(text, reply_markup=builder.as_markup())
    except Exception as e: logging.error(f"Error in show_numbers_page: {e}"); await message.answer(f"একটি ত্রুটি ঘটেছে: {e}")
@dp.callback_query(NavCallback.filter(F.action == "refresh"), UserStates.get_number_display)
async def handle_refresh_numbers(query: CallbackQuery, state: FSMContext):
    await show_numbers_page(query.message, state, edit=True); await query.answer()
@dp.callback_query(NavCallback.filter(F.action == "change_country"), UserStates.get_number_display)
async def handle_change_country(query: CallbackQuery, state: FSMContext):
    data = await state.get_data(); service_name = data.get("service_name")
    if not service_name: await state.clear(); await query.message.edit_text("ত্রুটি। /start দিন।"); return
    await state.set_state(UserStates.get_number_select_country); await query.message.edit_text(f"সার্ভিস: {service_name}\n\nকোন দেশের নম্বর চান?", reply_markup=get_countries_keyboard(service_name, action_prefix="select_for_get")); await query.answer()
@dp.callback_query(NavCallback.filter(F.action == "change_service"), UserStates.get_number_display)
async def handle_change_service(query: CallbackQuery, state: FSMContext):
    await state.set_state(UserStates.get_number_select_service); await query.message.edit_text("আপনি কোন সার্ভিসের জন্য নম্বর চান?", reply_markup=get_services_keyboard(action_prefix="select_for_get")); await query.answer()

# --- ৮. USER/ADMIN: Support ---
@dp.message(F.text == "🆘 Support", StateFilter(None))
async def handle_support(message: Message, state: FSMContext):
    support_keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="👨‍💻 Admin-এর সাথে যোগাযোগ করুন", url=f"t.me/{ADMIN_USERNAME}")]])
    await message.answer("সাপোর্টের জন্য, অনুগ্রহ করে নিচের বাটনে ক্লিক করে অ্যাডমিনের সাথে যোগাযোগ করুন:", reply_markup=support_keyboard)

# --- ব্যাক বাটন হ্যান্ডলার ---
@dp.callback_query(NavCallback.filter(F.action == "back"))
async def handle_back_button(query: CallbackQuery, callback_data: NavCallback, state: FSMContext):
    current_state_str = await state.get_state()
    if not current_state_str: await query.answer("কিছু করার নেই।", show_alert=True); return
    data = await state.get_data(); service_name = data.get("service_name"); country_name = data.get("country_name") 
    if current_state_str in [AdminStates.add_number_input_text.state, AdminStates.add_number_input_file.state]:
        await state.set_state(AdminStates.add_number_method_choice); method_keyboard = InlineKeyboardBuilder(); method_keyboard.row(InlineKeyboardButton(text="✍️ Add via Text", callback_data="add_num:text")); method_keyboard.row(InlineKeyboardButton(text="📄 Add via Text File", callback_data="add_num:file")); method_keyboard.row(InlineKeyboardButton(text="🔙 Back to Countries", callback_data=NavCallback(action="back").pack()))
        await query.message.edit_text(f"<b>সার্ভিস: {service_name}</b>\n<b>দেশ: {country_name}</b>\n\nআপনি কিভাবে নম্বর যোগ করতে চান? (টেক্সট বা ফাইল)", reply_markup=method_keyboard.as_markup())
    elif current_state_str == AdminStates.add_number_method_choice.state:
        await state.set_state(AdminStates.add_number_select_country); await query.message.edit_text(f"সার্ভিস: {service_name}\n\nকোন দেশে নম্বর যোগ করতে চান?", reply_markup=get_countries_keyboard(service_name, action_prefix="select_for_add_num"))
    elif current_state_str in [AdminStates.add_country_name.state, AdminStates.add_number_select_country.state, UserStates.get_number_select_country.state, AdminStates.remove_country_select.state]:
        if current_state_str == UserStates.get_number_select_country.state: new_state, action = UserStates.get_number_select_service, "select_for_get"
        elif current_state_str == AdminStates.add_country_name.state: new_state, action = AdminStates.add_country_select_service, "select_for_add_country"
        elif current_state_str == AdminStates.remove_country_select.state: new_state, action = AdminStates.remove_country_select_service, "select_for_remove_country"
        else: new_state, action = AdminStates.add_number_select_service, "select_for_add_num"
        await state.set_state(new_state); await query.message.edit_text("কোন সার্ভিসে কাজ করতে চান?", reply_markup=get_services_keyboard(action_prefix=action))
    else: await state.clear(); await query.message.edit_text("অপারেশন বাতিল করা হয়েছে।")
    await query.answer()

# --- জেনেরিক বাটন হ্যান্ডলার (none) ---
@dp.callback_query(F.data == "none")
async def handle_none_callback(query: CallbackQuery):
    await query.answer("এই বাটনে কোনো কাজ নেই।")


# --- ⚠️ নতুন: Flask সার্ভারকে থ্রেডে চালু করা ---
app = Flask(__name__)

@app.route('/')
def index():
    """Render-এর হেলথ চেকের জন্য একটি সিম্পল রুট।"""
    return "Bot is alive!"

def run_flask():
    """Flask সার্ভারকে একটি আলাদা থ্রেডে চালানোর জন্য।"""
    # Gunicorn-এর বদলে Flask-এর নিজস্ব সার্ভার ব্যবহার করা হচ্ছে
    # এটি Render-এর দেওয়া $PORT-এ চলবে
    app.run(host='0.0.0.0', port=RENDER_PORT)

# --- ⚠️ নতুন: বটকে Main Thread-এ চালু করা ---
async def main_polling():
    """বটের পোলিং শুরু করার প্রধান async ফাংশন।"""
    logging.info("বট পোলিং শুরু হচ্ছে...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, drop_pending_updates=True)

if __name__ == "__main__":
    # Flask সার্ভারকে একটি আলাদা থ্রেডে চালু করা
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # টেলিগ্রাম বটকে প্রধান থ্রেডে (Main Thread) চালু করা
    # এটি 'set_wakeup_fd' error-এর সমাধান করবে
    try:
        logging.info("Flask সার্ভার একটি আলাদা থ্রেডে চালু হয়েছে...")
        asyncio.run(main_polling())
    except (KeyboardInterrupt, SystemExit):
        logging.info("বট বন্ধ করা হলো।")
    except Exception as e:
        logging.critical(f"বট ক্র্যাশ করেছে: {e}", exc_info=True)

