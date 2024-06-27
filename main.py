from flask import Flask, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from forms import RegisterForm, LoginForm
import stripe
import os
from dotenv import load_dotenv

load_dotenv()
stripe.api_key = os.getenv('SECRET_KEY')

app = Flask(__name__)
app.config['SECRET_KEY'] = '8BYkEfBA6O6donzWlSihBXox7C0sKR6b'
Bootstrap5(app)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///data.db'
db = SQLAlchemy()
db.init_app(app)

# CONFIGURE Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(100))
    chart = db.relationship('Chart', back_populates='parent_user')


class Product(db.Model):
    __tablename__ = "products"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String())
    price = db.Column(db.Integer)
    description = db.Column(db.String())
    category = db.Column(db.String())
    image = db.Column(db.String())
    rating = db.Column(db.String())
    count = db.Column(db.String())


class Chart(db.Model):
    __tablename__ = 'charts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    parent_user = db.relationship('User', back_populates='chart', uselist=False)
    products = db.relationship('Goods', back_populates='parent_chart')


class Goods(db.Model):
    __tablename__ = 'goods'
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer)
    quantity = db.Column(db.Integer)
    image = db.Column(db.String)
    name = db.Column(db.String)
    price = db.Column(db.Integer)
    chart_id = db.Column(db.Integer, db.ForeignKey('charts.id'))
    parent_chart = db.relationship('Chart', back_populates='products')


with app.app_context():
    db.create_all()


@app.route("/", methods=["GET", "POST"])
def home():
    products = db.session.execute(db.select(Product)).scalars()
    categories = db.session.execute(db.select(Product).group_by(Product.category)).scalars()
    return render_template('index.html', products=products, categories=categories)


@app.route("/register", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = result.scalar()
        if user:
            flash("You've already signed up with that email, log in instead!")
            return redirect(url_for('login'))
        hash_and_salted_password = generate_password_hash(
            form.password.data,
            method='pbkdf2:sha256',
            salt_length=8
        )
        new_user = User(
            email=form.email.data,
            name=form.name.data,
            password=hash_and_salted_password,
        )
        db.session.add(new_user)
        db.session.commit()
        login_user(new_user)
        with app.app_context():
            new_chart = Chart(
                user_id=current_user.id
            )
            db.session.add(new_chart)
            db.session.commit()
        return redirect(url_for('home'))
    return render_template("register.html", form=form, current_user=current_user)


@app.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        password = form.password.data
        result = db.session.execute(db.select(User).where(User.email == form.email.data))
        user = result.scalar()
        if not user:
            flash("That email doesn't exist, please try again.")
            return redirect(url_for('login'))
        elif not check_password_hash(user.password, password):
            flash("Password incorrect, please try again.")
            return redirect(url_for('login'))
        else:
            login_user(user)
            return redirect(url_for('home'))
    return render_template("login.html", form=form, current_user=current_user)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/products/<product_id>')
def product_info(product_id):
    requested_product = db.session.execute(db.select(Product).where(Product.id == product_id)).scalar()
    return render_template("product.html", product=requested_product)


@app.route('/categories/<category_name>')
def category(category_name):
    requested_category = db.session.execute(db.select(Product).where(Product.category == category_name)).scalars()
    return render_template('category.html', categories=requested_category)


@app.route('/products')
def all_products():
    products = db.session.execute(db.select(Product).order_by(Product.title)).scalars()
    return render_template('all_products.html', products=products)


@app.route('/chart')
def chart():
    if current_user.is_authenticated:
        user_chart = db.session.execute(db.Select(Chart).where(Chart.user_id == current_user.id)).scalar().products
        total_bill = 0
        for product in user_chart:
            total_bill += product.quantity*product.price
    else:
        return redirect(url_for('login'))

    return render_template('chart.html', goods=user_chart, total=round(total_bill, 2))


@app.route('/add_product/<product_id>')
def add_to_chart(product_id):
    requested_product = db.session.execute(db.select(Product).where(Product.id == product_id)).scalar()
    if current_user.is_authenticated:
        if int(requested_product.count) < 1:
            flash('Unfortunately the product is out of stock now')
            return redirect(url_for('product_info', product_id=requested_product.id))
        requested_chart = db.session.execute(db.select(Chart).where(Chart.user_id == current_user.id)).scalar()

        with app.app_context():
            new_good = Goods(
                image=requested_product.image,
                price=requested_product.price,
                name=requested_product.title,
                quantity=1,
                chart_id=requested_chart.id,
                product_id=requested_product.id
            )
            db.session.add(new_good)
            db.session.commit()
    else:
        return redirect(url_for('login'))
    return redirect(url_for('product_info', product_id=requested_product.id))


@app.route('/delete/<goods_id>')
@login_required
def delete_from_chart(goods_id):
    with app.app_context():
        goods_del = db.session.execute(db.Select(Goods).where(Goods.id == goods_id)).scalar()
        db.session.delete(goods_del)
        db.session.commit()
    return redirect(url_for('chart'))


@app.route('/increase/<goods_id>', methods=['GET'])
@login_required
def increase_quantity(goods_id):
    with app.app_context():
        goods_to_update = db.session.execute(db.Select(Goods).where(Goods.id == goods_id)).scalar()
        product_count = int(db.session.execute(db.Select(Product).where(Product.id == goods_to_update.product_id)).scalar().count)
        if product_count > 1:
            goods_to_update.quantity += 1
            db.session.commit()
    return redirect(url_for('chart'))


@app.route('/decrease/<goods_id>')
@login_required
def decrease_quantity(goods_id):
    with app.app_context():
        goods_to_update = db.session.execute(db.Select(Goods).where(Goods.id == goods_id)).scalar()
        if goods_to_update.quantity > 1:
            goods_to_update.quantity -= 1
            db.session.commit()
    return redirect(url_for('chart'))


@app.route('/change/<goods_id>', methods=['GET', 'POST'])
@login_required
def change_quantity(goods_id):
    required_quantity = request.form['quantity']
    with app.app_context():
        goods_to_update = db.session.execute(db.Select(Goods).where(Goods.id == goods_id)).scalar()
        product_count = db.session.execute(db.Select(Product).where(Product.id == goods_to_update.product_id)).scalar().count

        if request.method == 'POST':
            if required_quantity > product_count:
                flash(f"We don't have enough quantity of '{goods_to_update.name}':  {product_count} "
                      f"is available")
                return redirect(url_for('chart'))
            goods_to_update.quantity = required_quantity
            db.session.commit()
    return redirect(url_for('chart'))


@app.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    user_chart = db.session.execute(db.Select(Chart).where(Chart.user_id == current_user.id)).scalar().products
    items = []
    for product in user_chart:
        items.append(
            {"price": stripe.Product.search(query=f'active: "true" AND name:"{product.name}"', limit=1)
            ['data'][0]['default_price'], "quantity": product.quantity}
        )
    checkout_session = stripe.checkout.Session.create(
        success_url=url_for('success', _external=True),
        line_items=items,
        mode="payment"
    )
    return redirect(checkout_session.url, code=303)


@app.route('/success')
@login_required
def success():
    with app.app_context():
        user_chart = db.session.execute(db.Select(Chart).where(Chart.user_id == current_user.id)).scalar().products
        for goods in user_chart:
            product_to_update = db.session.execute(db.Select(Product).where(Product.id == goods.product_id)).scalar()
            product_to_update.count = int(product_to_update.count) - goods.quantity
            db.session.delete(goods)
            db.session.commit()
    return render_template('success.html')


@app.route('/search_product', methods=['GET', 'POST'])
def search_product():
    search = request.form.get('name')
    products = db.session.execute(db.Select(Product).where(Product.title.like(f'%{search}%'))).scalars()
    if db.session.execute(db.Select(Product).where(Product.title.like(f'%{search}%'))).scalar() is None:
        flash("Unfortunately nothing was found")
        return redirect(url_for('all_products'))
    return render_template('list_of_products.html', products=products)


if __name__ == "__main__":
    app.run(debug=True, port=501)