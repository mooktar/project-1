import os
import requests
import json

from flask import Flask, session, render_template, request, url_for, redirect, flash, abort
from flask_session import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

app = Flask(__name__)

# Check for environment variable
if not os.getenv("DATABASE_URL"):
    raise RuntimeError("DATABASE_URL is not set")

# Configure session to use filesystem
app.config['DEBUG'] = True
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Set up database
engine = create_engine(os.getenv("DATABASE_URL"))
db = scoped_session(sessionmaker(bind=engine))

# Goodreads key
gkey = "7VnVDfnoHsxw0rTMaQciw"


@app.route("/", methods=["GET", "POST"])
def index():
    """Home page"""

    sql = "SELECT * FROM books"
    # List books depending by user's login
    if session.get('logged_in') and request.method == "POST":
        search = request.form.get("search")
        sql += " WHERE isbn LIKE '%{}%' OR title LIKE '%{}%' OR author LIKE '%{}%'".format(
            search, search.capitalize(), search.capitalize())
        books = db.execute(sql).fetchall()
    else:
        sql += " ORDER BY title ASC LIMIT 100"
        books = db.execute(sql).fetchall()

    return render_template("index.html", books=books)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Create session for registered user"""

    error = False
    errinfo = None

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Chack error on inputs and existing users
        if (username is None) or (password is None):
            error = True
            errinfo = "Username or Password is required."

        user = db.execute(
            "SELECT name, password FROM users WHERE name = :username AND password = :password",
            {"username": username, "password": password}
        ).fetchone()
        if not user:
            error = True
            errinfo = f"{username} is not exists."
        else:
            # Create session
            session["username"] = username
            session['logged_in'] = True
            return redirect(url_for('index'))

        flash(errinfo)
        return redirect(url_for('login'))

    return render_template("login.html", error=error, info=errinfo)


@app.route("/logout")
def logout():
    # Destroy current session
    session.pop('username', None)
    session['logged_in'] = False
    return redirect(url_for('index'))


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register new user"""

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        error = False
        errinfo = None
        sql = db.execute("SELECT name, password FROM users WHERE name = :name", {
                         "name": username}).fetchone()
        # Ckaeck user exists and inputs.
        if username is None or password is None:
            error = True
            errinfo = "Error inputs."
            return render_template('register.html', error=error, info=errinfo)
        elif db.execute("SELECT COUNT(*) FROM users WHERE name = :name", {"name": username}).fetchall().count == 1:
            error = True
            errinfo = f"username {username} already exists."
        else:
            db.execute("INSERT INTO users (name, password) VALUES (:name, :password)", {
                       "name": username, "password": password})
            db.commit()
            return redirect(url_for('login'))

        flash(error)
    return render_template("register.html")


@app.route("/book")
@app.route("/book/<isbn>", methods=["GET", "POST"])
def book(isbn):
    """About a single book."""

    # Make sure book exists
    book = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                      {"isbn": isbn}).fetchone()
    if book is None:
        return redirect(url_for('index'))

    # Get res and reviews informations
    res = requests.get("https://www.goodreads.com/book/review_counts.json",
                       params={"key": gkey, "isbns": book.isbn}).json()
    reviews = db.execute(
        "SELECT rating, message, name FROM reviwes JOIN users ON users.id = reviews.user_id WHERE book_id = :book_id", {"book_id": book.id}).fetchall()

    # Get users information and its relative post
    posted = False
    log = session.get('logged_in')
    user = None
    if log is True:
        user = db.execute("SELECT id, name FROM users WHERE name = :name", {
            "name": session["username"]}).fetchone()

    if (log is True) and (db.execute("SELECT book_id FROM reviews WHERE book_id = :book_id", {"book_id": book.id}).rowcount == 1):
        posted = True

    # Post a review
    error = "Enter your review"
    if request.method == "POST":
        rating = request.form.get("rating")
        message = request.form.get("message")

        if message is None:
            error = "Please fill this textarea."
        else:
            db.execute("INSERT INTO reviews (user_id, book_id, rating, message) VALUES (:user_id, :book_id, :rating, :message)", {
                "user_id": user.id, "book_id": book.id, "rating": rating, "message": message})
            db.commit()
            db.close()

        return redirect(url_for('book', isbn=book.isbn))

    return render_template("book.html", book=book, res=res, reviews=reviews, posted=posted, error=error)


@app.route("/api")
@app.route("/api/<isbn>", methods=["GET", "POST"])
def api(isbn):
    """Get json informations for book"""

    if request.method == "GET":
        book = db.execute("SELECT * FROM books WHERE isbn = :isbn",
                          {"isbn": isbn}).fetchone()
        if isbn is None or book is None:
            return abort(404)

        res = requests.get("https://www.goodreads.com/book/review_counts.json",
                           params={"key": gkey, "isbns": isbn}).json()

        apires = {
            "ttile": book.title,
            "author": book.author,
            "year": book.year,
            "isbn": book.isbn,
            "review count": res['books'][0]['work_ratings_count'],
            "average score": res['books'][0]['average_rating']
        }

    return render_template("api.html", book=book, apires=json.dumps(apires))


if __name__ == "__main__":
    app.run(debug=True)
