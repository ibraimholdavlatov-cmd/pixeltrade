import os
from datetime import datetime, timedelta
from flask import Flask, render_template, request, redirect, url_for, flash, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy import func

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pixeltrade.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

UPLOAD_FOLDER = os.path.join('static', 'product_images')
AVATAR_FOLDER = os.path.join('static', 'avatars')
for folder in [UPLOAD_FOLDER, AVATAR_FOLDER]:
    os.makedirs(folder, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['AVATAR_FOLDER'] = AVATAR_FOLDER

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
# Добавляем строку ниже
login_manager.login_message = "Пожалуйста, войдите в аккаунт, чтобы получить доступ к этой странице."

# --- КОНСТАНТЫ ---
SERVICE_FEE = 0.05  
WITHDRAW_FEE = 0.02 

# --- МОДЕЛИ ---
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), default='user') # user / admin
    description = db.Column(db.Text, default="Новый пользователь PixelTrade")
    avatar = db.Column(db.String(100), default='default.png')
    balance = db.Column(db.Float, default=0.0)
    
    # Поле для кулдауна сообщений в поддержке
    last_ticket_msg_at = db.Column(db.DateTime, nullable=True)

    products = db.relationship('Product', backref='user', lazy=True)
    # Строка с tickets удалена, связь настроена в классе Ticket через backref='tickets'

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    short_description = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    image = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False, default="Предметы") 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='active')

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), default='paid') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    payment_method = db.Column(db.String(50))
    price_at_purchase = db.Column(db.Float) 
    fee_amount = db.Column(db.Float, default=0.0)
    
    product = db.relationship('Product', backref='order_info', lazy=True)
    buyer = db.relationship('User', foreign_keys=[buyer_id], backref='my_purchases_list')
    seller = db.relationship('User', foreign_keys=[seller_id], backref='my_sales_list')
    review = db.relationship('Review', backref='order', uselist=False)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    seller_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    buyer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    buyer = db.relationship('User', foreign_keys=[buyer_id])

class Chat(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user1_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user2_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user1 = db.relationship('User', foreign_keys=[user1_id])
    user2 = db.relationship('User', foreign_keys=[user2_id])
    messages = db.relationship('Message', backref='chat', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    chat_id = db.Column(db.Integer, db.ForeignKey('chat.id'))
    sender = db.relationship('User')

class Ticket(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    subject = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    status = db.Column(db.String(20), default='Open') 
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Новые поля
    last_update = db.Column(db.DateTime, default=datetime.utcnow)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True) # Кто из админов взял тикет
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # Исправленные связи
    # backref='tickets' позволит обращаться к тикетам юзера через user.tickets
    user = db.relationship('User', foreign_keys=[user_id], backref='tickets')
    
    # assigned_admin позволяет видеть, какой админ привязан к тикету
    assigned_admin = db.relationship('User', foreign_keys=[admin_id])
    
    messages = db.relationship('TicketMessage', backref='ticket', lazy=True, cascade="all, delete-orphan")

class TicketMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('ticket.id'), nullable=False)
    # Исправлено: sender_id теперь всегда ссылается на реального User.id
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) 
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Исправлено: упрощенная и чистая связь
    sender = db.relationship('User', foreign_keys=[sender_id])

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- ФИЛЬТРЫ ШАБЛОНОВ ---
@app.template_filter('format_price')
def format_price(value):
    try:
        return "{:,.0f} ₽".format(value).replace(',', ' ')
    except (ValueError, TypeError):
        return f"{value} ₽"

@app.template_filter('human_date')
def human_date(value):
    if not value: return ""
    now = datetime.utcnow()
    diff = now - value
    months = {1: 'января', 2: 'февраля', 3: 'марта', 4: 'апреля', 5: 'мая', 6: 'июня',
              7: 'июля', 8: 'августа', 9: 'сентября', 10: 'октября', 11: 'ноября', 12: 'декабря'}
    if diff.days == 0: return f"Сегодня в {value.strftime('%H:%M')}"
    elif diff.days == 1: return f"Вчера в {value.strftime('%H:%M')}"
    else: return f"{value.day} {months[value.month]} в {value.strftime('%H:%M')}"

# --- АДМИН-МАРШРУТЫ ---

@app.route('/owner-panel')
@login_required
def owner_panel():
    if current_user.username != 'mersiyan':
        abort(403)
    u_count = User.query.count()
    o_count = Order.query.filter_by(status='completed').count()
    turnover = db.session.query(db.func.sum(Order.price_at_purchase)).filter_by(status='completed').scalar() or 0
    
    return render_template('admin/owner_panel.html', users_count=u_count, orders_count=o_count, total_turnover=turnover)

@app.route('/admin-panel')
@login_required
def admin_panel():
    if current_user.role != 'admin' and current_user.username != 'mersiyan':
        abort(403)
    
    # Получаем запрос из поисковой строки
    search_query = request.args.get('search', '')
    
    # Создаем базовый запрос с присоединением таблицы User для поиска по автору тикета
    query = Ticket.query.join(User, Ticket.user_id == User.id)
    
    if search_query:
        # Фильтруем по ID тикета, теме или никнейму пользователя
        query = query.filter(
            (Ticket.id.contains(search_query)) | 
            (Ticket.subject.contains(search_query)) | 
            (User.username.contains(search_query))
        )

    # Сортировка: сначала открытые (False < True), потом по дате обновления
    all_tickets = query.order_by(
        Ticket.status == 'Closed', # Закрытые в конец
        Ticket.last_update.desc()  # Свежие наверх
    ).all()
    
    # Также передаем список всех пользователей с ролью admin или ником mersiyan для вкладки персонала
    staff = User.query.filter((User.role == 'admin') | (User.username == 'mersiyan')).all()
    
    return render_template('admin/admin_panel.html', tickets=all_tickets, staff=staff, search_query=search_query)

@app.route('/promote-user', methods=['POST'])
@login_required
def promote_user():
    if current_user.username != 'mersiyan':
        abort(403)
    
    target_username = request.form.get('username')
    user = User.query.filter_by(username=target_username).first()
    
    if user:
        user.role = 'admin'
        db.session.commit()
        flash(f'Пользователь {target_username} теперь администратор!')
    else:
        flash('Пользователь не найден')
        
    return redirect(url_for('admin_panel'))

# --- ОСНОВНЫЕ МАРШРУТЫ ---

@app.route('/')
def index():
    q = request.args.get('q')
    sort = request.args.get('sort')
    category = request.args.get('category') 
    query = Product.query.filter_by(status='active')
    if q:
        query = query.filter(Product.short_description.contains(q) | Product.description.contains(q))
    if category:
        query = query.filter_by(category=category)
    if sort == 'cheap': query = query.order_by(Product.price.asc())
    elif sort == 'expensive': query = query.order_by(Product.price.desc())
    else: query = query.order_by(Product.created_at.desc())
    return render_template('index.html', products=query.all())

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if User.query.filter_by(username=username).first():
            flash('Пользователь уже существует')
            return redirect(url_for('register'))
        new_user = User(username=username, password=generate_password_hash(password))
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        return redirect(url_for('profile_center'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            login_user(user)
            return redirect(url_for('profile_center'))
        flash('Неверный логин или пароль')
    return render_template('login.html')

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/sell', methods=['GET', 'POST'])
@login_required
def sell():
    if request.method == 'POST':
        file = request.files.get('image')
        title = request.form.get('short_description')
        price = request.form.get('price')
        category = request.form.get('category')
        if file and title and price:
            filename = secure_filename(file.filename)
            unique_name = f"{datetime.now().timestamp()}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            new_product = Product(
                short_description=title,
                description=request.form.get('description'),
                price=float(price),
                category=category,
                image=unique_name,
                user_id=current_user.id
            )
            db.session.add(new_product)
            db.session.commit()
            flash('Товар успешно выставлен на продажу!')
            return redirect(url_for('profile_center'))
    return render_template('sell.html')

@app.route('/profile-center')
@login_required
def profile_center():
    user_products = Product.query.filter(Product.user_id == current_user.id, Product.status != 'archived').order_by(Product.created_at.desc()).all()
    products_count = Product.query.filter_by(user_id=current_user.id, status='active').count()
    total_value = db.session.query(db.func.sum(Product.price)).filter(Product.user_id == current_user.id, Product.status == 'active').scalar() or 0
    
    reviews_count = Review.query.filter_by(seller_id=current_user.id).count()
    display_rating = None
    if reviews_count >= 5:
        avg_val = db.session.query(func.avg(Review.rating)).filter(Review.seller_id == current_user.id).scalar()
        display_rating = round(avg_val, 1)

    return render_template('profile_center.html', 
                           products=user_products, 
                           products_count=products_count, 
                           total_value=total_value,
                           display_rating=display_rating,
                           reviews_count=reviews_count)

@app.route('/api/my-reviews')
@login_required
def get_my_reviews_api():
    offset = request.args.get('offset', 0, type=int)
    limit = 10
    reviews = Review.query.filter_by(seller_id=current_user.id)\
        .order_by(Review.created_at.desc())\
        .offset(offset).limit(limit).all()
    
    reviews_list = []
    for r in reviews:
        reviews_list.append({
            'buyer': r.buyer.username,
            'rating': r.rating,
            'text': r.text,
            'date': r.created_at.strftime('%d.%m.%Y')
        })
    return {'reviews': reviews_list}

@app.route('/user/<int:user_id>')
def public_profile(user_id):
    user = User.query.get_or_404(user_id)
    reviews = Review.query.filter_by(seller_id=user.id).order_by(Review.created_at.desc()).all()
    reviews_count = len(reviews)
    
    display_rating = None
    if reviews_count >= 5:
        avg_val = db.session.query(func.avg(Review.rating)).filter(Review.seller_id == user.id).scalar()
        display_rating = round(avg_val, 1)
        
    products = Product.query.filter_by(user_id=user.id, status='active').order_by(Product.created_at.desc()).all()
    return render_template('public_profile.html', user=user, products=products, display_rating=display_rating, reviews_count=reviews_count, reviews=reviews)

@app.route('/confirm-order/<int:order_id>', methods=['POST'])
@login_required
def confirm_order(order_id):
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != current_user.id: 
        abort(403)
    
    if order.status == 'paid':
        seller = User.query.get(order.seller_id)
        # Рассчитываем сумму и округляем до 2 знаков
        amount_to_seller = round(order.price_at_purchase * (1 - SERVICE_FEE), 2)
        fee_amount = round(order.price_at_purchase * SERVICE_FEE, 2)
        
        seller.balance += amount_to_seller
        order.status = 'completed'
        order.fee_amount = fee_amount
        
        db.session.commit()
        flash(f'Заказ подтвержден! Продавцу начислено {amount_to_seller} ₽')
    
    return redirect(url_for('my_purchases'))

@app.route('/leave-review/<int:order_id>', methods=['POST'])
@login_required
def leave_review(order_id):
    order = Order.query.get_or_404(order_id)
    if order.buyer_id != current_user.id or order.status != 'completed': 
        abort(403)
    
    rating = request.form.get('rating')
    text = request.form.get('text')
    
    if rating:
        new_review = Review(
            order_id=order.id, 
            seller_id=order.seller_id, 
            buyer_id=current_user.id, 
            rating=int(rating), 
            text=text
        )
        db.session.add(new_review)
        db.session.commit()
        flash('Благодарим за отзыв!')
        
    return redirect(url_for('my_purchases'))

@app.route('/edit-review/<int:review_id>', methods=['POST'])
@login_required
def edit_review(review_id):
    review = Review.query.get_or_404(review_id)
    if review.buyer_id != current_user.id: abort(403)
    
    review.rating = int(request.form.get('rating'))
    review.text = request.form.get('text')
    db.session.commit()
    flash('Отзыв обновлен!')
    return redirect(url_for('my_purchases'))

@app.route('/delete-review/<int:review_id>', methods=['POST'])
@login_required
def delete_review(review_id):
    review = Review.query.get_or_404(review_id)
    if review.buyer_id != current_user.id: abort(403)
    
    db.session.delete(review)
    db.session.commit()
    flash('Отзыв успешно удален')
    return redirect(url_for('my_purchases'))

@app.route('/toggle-status/<int:product_id>', methods=['POST'])
@login_required
def toggle_status(product_id):
    product = Product.query.get_or_404(product_id)
    if product.user_id != current_user.id: abort(403)
    if product.status == 'active':
        product.status = 'inactive'
        flash('Товар снят с продажи')
    elif product.status == 'inactive':
        product.status = 'active'
        flash('Товар выставлен на продажу')
    db.session.commit()
    return redirect(url_for('profile_center'))

@app.route('/buy/<int:product_id>', methods=['POST'])
@login_required
def buy_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.user_id == current_user.id:
        flash('Нельзя купить свой товар')
        return redirect(url_for('product_detail', product_id=product.id))
    if product.status != 'active':
        flash('Товар недоступен')
        return redirect(url_for('index'))
    return render_template('checkout.html', product=product)

@app.route('/confirm_payment/<int:product_id>', methods=['POST'])
@login_required
def confirm_payment(product_id):
    product = Product.query.get_or_404(product_id)
    method = request.form.get('payment_method')
    
    order = Order(product_id=product.id, buyer_id=current_user.id, seller_id=product.user_id, payment_method=method, price_at_purchase=product.price)
    product.status = 'sold'
    db.session.add(order)
    
    chat = Chat.query.filter(((Chat.user1_id == current_user.id) & (Chat.user2_id == product.user_id)) | 
                             ((Chat.user1_id == product.user_id) & (Chat.user2_id == current_user.id))).first()
    if not chat:
        chat = Chat(user1_id=current_user.id, user2_id=product.user_id)
        db.session.add(chat)
    
    db.session.flush()
    sys_msg = Message(text=f"📢 СИСТЕМА: Товар '{product.short_description}' оплачен.", sender_id=None, chat_id=chat.id)
    db.session.add(sys_msg)
    db.session.commit()
    flash('Оплата прошла успешно! Вы можете связаться с продавцом в чате.')
    return redirect(url_for('chat', chat_id=chat.id))

@app.route('/my-purchases')
@login_required
def my_purchases():
    purchases = Order.query.filter_by(buyer_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('my_purchases.html', purchases=purchases)

@app.route('/product/<int:product_id>')
def product_detail(product_id):
    product = Product.query.get_or_404(product_id)
    return render_template('product_detail.html', product=product, seller=product.user)

@app.route('/delete-product/<int:product_id>', methods=['POST'])
@login_required
def delete_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.user_id != current_user.id: abort(403)
    product.status = 'archived'
    db.session.commit()
    flash('Товар удален из вашего списка')
    return redirect(url_for('profile_center'))

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.description = request.form.get('description')
        file = request.files.get('avatar')
        if file:
            filename = secure_filename(file.filename)
            unique_name = f"av_{current_user.id}_{filename}"
            file.save(os.path.join(app.config['AVATAR_FOLDER'], unique_name))
            current_user.avatar = unique_name
        db.session.commit()
        flash('Профиль обновлен')
    return render_template('profile.html', user=current_user)

@app.route('/withdraw', methods=['POST'])
@login_required
def withdraw():
    amount = float(request.form.get('amount', 0))
    if amount <= 0 or amount > current_user.balance:
        flash('Недостаточно средств')
    else:
        final_amount = amount * (1 - WITHDRAW_FEE)
        current_user.balance -= amount
        db.session.commit()
        flash(f'Вывод {final_amount} ₽ заказан')
    return redirect(url_for('profile_center'))

@app.route('/chats')
@login_required
def chat_list():
    chats = Chat.query.filter((Chat.user1_id == current_user.id) | (Chat.user2_id == current_user.id)).all()
    return render_template('chat_list.html', chats=chats)

@app.route('/start_chat/<int:user_id>', methods=['POST'])
@login_required
def start_chat(user_id):
    chat = Chat.query.filter(((Chat.user1_id == current_user.id) & (Chat.user2_id == user_id)) | ((Chat.user1_id == user_id) & (Chat.user2_id == current_user.id))).first()
    if not chat:
        chat = Chat(user1_id=current_user.id, user2_id=user_id)
        db.session.add(chat)
        db.session.commit()
    return redirect(url_for('chat', chat_id=chat.id))

@app.route('/chat/<int:chat_id>', methods=['GET', 'POST'])
@login_required
def chat(chat_id):
    chat_obj = Chat.query.get_or_404(chat_id)
    if request.method == 'POST':
        text = request.form.get('text')
        if text:
            msg = Message(text=text, sender_id=current_user.id, chat_id=chat_id)
            db.session.add(msg)
            db.session.commit()
            return redirect(url_for('chat', chat_id=chat_id))
    messages = Message.query.filter_by(chat_id=chat_id).order_by(Message.timestamp.asc()).all()
    return render_template('chat.html', chat=chat_obj, messages=messages)

@app.route('/my-sales')
@login_required
def my_sales():
    sales = Order.query.filter_by(seller_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template('my_sales.html', sales=sales)

@app.route('/edit-product/<int:product_id>', methods=['GET', 'POST'])
@login_required
def edit_product(product_id):
    product = Product.query.get_or_404(product_id)
    if product.user_id != current_user.id: abort(403)
    
    if request.method == 'POST':
        product.short_description = request.form.get('short_description')
        product.description = request.form.get('description')
        product.price = float(request.form.get('price'))
        product.category = request.form.get('category')
        
        file = request.files.get('image')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            unique_name = f"{datetime.now().timestamp()}_{filename}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], unique_name))
            product.image = unique_name
            
        db.session.commit()
        flash('Товар обновлен')
        return redirect(url_for('profile_center'))
    
    return render_template('edit_product.html', product=product)

@app.route('/rules')
def rules():
    return render_template('rules.html')

# --- СИСТЕМА ТИКЕТОВ ---

@app.route('/support')
@login_required
def support():
    user_tickets = Ticket.query.filter_by(user_id=current_user.id).order_by(Ticket.created_at.desc()).all()
    return render_template('support.html', tickets=user_tickets)

@app.route('/create_ticket', methods=['POST'])
@login_required
def create_ticket():
    # 1. Проверка лимита открытых тикетов (Максимум 3)
    open_tickets_count = Ticket.query.filter_by(user_id=current_user.id).filter(Ticket.status != 'Closed').count()
    if open_tickets_count >= 3:
        flash("У вас уже открыто 3 активных тикета. Дождитесь закрытия.")
        return redirect(url_for('support'))

    category = request.form.get('category')
    subject = request.form.get('subject')
    message_text = request.form.get('message')

    if not subject or not message_text:
        flash("Пожалуйста, заполните все поля.")
        return redirect(url_for('support'))

    new_ticket = Ticket(subject=subject, category=category, user_id=current_user.id)
    db.session.add(new_ticket)
    db.session.flush() 

    first_msg = TicketMessage(ticket_id=new_ticket.id, sender_id=current_user.id, text=message_text)
    db.session.add(first_msg)
    
    # Обновляем время последнего сообщения пользователя
    current_user.last_ticket_msg_at = datetime.utcnow()
    
    db.session.commit()
    flash("Ваше обращение принято и находится на рассмотрении.")
    return redirect(url_for('support'))

@app.route('/ticket/<int:ticket_id>', methods=['GET', 'POST'])
@login_required
def view_ticket(ticket_id):
    ticket = Ticket.query.get_or_404(ticket_id)
    # Никнейм "mersiyan" всегда является владельцем
    is_admin = (current_user.role == 'admin' or current_user.username == 'mersiyan')
    
    if ticket.user_id != current_user.id and not is_admin:
        abort(403)
        
    if request.method == 'POST':
        if not is_admin:
            if current_user.last_ticket_msg_at:
                diff = datetime.utcnow() - current_user.last_ticket_msg_at
                if diff.total_seconds() < 180:
                    flash(f"Пожалуйста, подождите {int(180 - diff.total_seconds())} сек.")
                    return redirect(url_for('view_ticket', ticket_id=ticket.id))
        
        text = request.form.get('text')
        if text:
            # Создаем сообщение от текущего пользователя (hello или mersiyan)
            new_msg = TicketMessage(
                ticket_id=ticket.id, 
                sender_id=current_user.id, 
                text=text
            )
            
            # Логика статусов
            if is_admin and current_user.id != ticket.user_id:
                ticket.status = 'Answered'
                if not ticket.admin_id:
                    ticket.admin_id = current_user.id
            else:
                if ticket.status in ['Closed', 'Answered']:
                    ticket.status = 'Open'
                current_user.last_ticket_msg_at = datetime.utcnow()
            
            ticket.last_update = datetime.utcnow()
            db.session.add(new_msg)
            db.session.commit()
            return redirect(url_for('view_ticket', ticket_id=ticket.id))
            
    return render_template('ticket_chat.html', ticket=ticket)

@app.route('/ticket/<int:ticket_id>/toggle', methods=['POST'])
@login_required
def toggle_ticket(ticket_id):
    # Проверка прав: админ или владелец mersiyan
    if current_user.role != 'admin' and current_user.username != 'mersiyan':
        abort(403)
        
    ticket = Ticket.query.get_or_404(ticket_id)
    
    # Переключаем статус
    if ticket.status != 'Closed':
        ticket.status = 'Closed'
    else:
        ticket.status = 'Open'
    
    # Если за тикетом еще не закреплен админ, закрепляем текущего
    if not ticket.admin_id:
        ticket.admin_id = current_user.id
        
    ticket.last_update = datetime.utcnow()
    db.session.commit()
    
    flash(f"Статус тикета #{ticket.id} изменен на {ticket.status}")
    # Убедись, что название маршрута 'view_ticket' совпадает с твоим (иногда называют 'ticket_detail')
    return redirect(url_for('view_ticket', ticket_id=ticket.id))

if __name__ == "__main__":
    # Хост 0.0.0.0 обязателен, чтобы сервер слушал внешние запросы
    # Порт 80 — стандарт для Amvera
    app.run(host='0.0.0.0', port=80)
