import os
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
import core

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'

login_manager = LoginManager(app)
login_manager.login_view = 'login'  # redirect to login if user not authenticated

# Configure upload folder and allowed extensions
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Configure SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///imageresults.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# User model for authentication and gamification
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    points = db.Column(db.Integer, default=0)  # points earned for uploads

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Like(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_result_id = db.Column(db.Integer, db.ForeignKey('image_result.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'image_result_id', name='_user_image_uc'),)

class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    image_result_id = db.Column(db.Integer, db.ForeignKey('image_result.id'), nullable=False)
    
    # Optional: relationships for easier access
    user = db.relationship('User', backref='comments')
    image_result = db.relationship('ImageResult', backref='comments')


# Database model for storing image results
class ImageResult(db.Model):

    user = db.relationship('User', backref='uploads')
    likes = db.relationship('Like', backref='upload', lazy='dynamic')

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(200), nullable=False)
    label = db.Column(db.String(100), nullable=False)
    summary_text = db.Column(db.Text, nullable=True)
    stats_json = db.Column(db.Text, nullable=True)
    upload_time = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))  # Link to User
    location = db.Column(db.String(100), nullable=True)  # NEW field for area

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(300))
    awarded_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Optional: relationship back to user
    user = db.relationship('User', backref='achievements')


@login_manager.user_loader
def load_user(user_id):

    return User.query.get(int(user_id))

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            flash("Please provide both username and password")
            return redirect(url_for('register'))
        if User.query.filter_by(username=username).first():
            flash("Username already exists")
            return redirect(url_for('register'))
        new_user = User(username=username)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        flash("Registration successful. Please log in.")
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            flash("Logged in successfully!")
            return redirect(url_for('main'))
        else:
            flash("Invalid username or password")
            return redirect(url_for('login'))
    return render_template('login.html')

@app.route('/profile')
@login_required
def profile():
    # Get the current user's uploads, ordered by most recent
    uploads = ImageResult.query.filter_by(user_id=current_user.id).order_by(ImageResult.upload_time.desc()).all()
    return render_template('profile.html', user=current_user, uploads=uploads)


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("You have been logged out.")
    return redirect(url_for('main'))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Main page with two buttons: Upload and History
@app.route('/')
def main():
    return render_template('main.html')

# Upload page
@app.route('/upload', methods=['GET', 'POST'])
@login_required
def upload():
    if request.method == 'POST':
        if 'file' not in request.files:
            flash('No file part in the request')
            return redirect(request.url)
        file = request.files['file']
        if file.filename == '':
            flash('No file selected')
            return redirect(request.url)
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            file.save(file_path)
            try:
                label = core.classify_image_pytorch(file_path)
                stats_response = core.generate_species_stats_with_chatgpt(label)
                parts = stats_response.split("###")
                if len(parts) == 2:
                    stats_json_str = parts[0].strip()
                    summary_text = parts[1].strip()
                    try:
                        stats_table = json.loads(stats_json_str)
                    except Exception as e:
                        stats_table = None
                        summary_text = stats_response
                else:
                    stats_table = None
                    summary_text = stats_response
            except Exception as e:
                flash(f'Error processing the image: {e}')
                return redirect(request.url)
            
            # Get location from form (optional)
            location = request.form.get('location', None)
            
            new_result = ImageResult(filename=filename, label=label,
                                     summary_text=summary_text,
                                     stats_json=json.dumps(stats_table) if stats_table else None,
                                     user_id=current_user.id,
                                     location=location)
            db.session.add(new_result)
            
            # Award points (e.g., 10 points per upload)
            current_user.points += 10
            
            # Award first upload achievement if applicable...
            upload_count = ImageResult.query.filter_by(user_id=current_user.id).count()
            if upload_count == 1:
                if not UserAchievement.query.filter_by(user_id=current_user.id, achievement_name="First Upload").first():
                    new_achievement = UserAchievement(
                        user_id=current_user.id,
                        achievement_name="First Upload",
                        description="Congratulations on uploading your first image!"
                    )
                    db.session.add(new_achievement)
                    flash("Achievement unlocked: First Upload!")
                    
            db.session.commit()
            return render_template('result.html', label=label,
                                   summary_text=summary_text,
                                   stats_table=stats_table,
                                   image_filename=filename)
    return render_template('upload.html')

@app.route('/upload/<int:upload_id>', methods=['GET', 'POST'])
@login_required
def upload_detail(upload_id):
    upload = ImageResult.query.get_or_404(upload_id)
    
    # Handle new comment submission
    if request.method == 'POST':
        content = request.form.get('content')
        if content:
            new_comment = Comment(content=content, user_id=current_user.id, image_result_id=upload_id)
            db.session.add(new_comment)
            db.session.commit()
            flash("Comment added!")
            return redirect(url_for('upload_detail', upload_id=upload_id))
        else:
            flash("Please enter some text for your comment.")
    
    # Fetch comments for this upload, ordered by timestamp ascending
    comments = Comment.query.filter_by(image_result_id=upload_id).order_by(Comment.timestamp.asc()).all()
    return render_template('upload_detail.html', upload=upload, comments=comments)

@app.route('/feed')
@login_required
def feed():
    # Get an optional location filter from query parameters
    query_location = request.args.get('location', None)
    if query_location:
         # Perform a case-insensitive match on the location field
         results = ImageResult.query.filter(
             ImageResult.location.ilike(f"%{query_location}%")
         ).order_by(ImageResult.upload_time.desc()).all()
    else:
         # If no filter provided, show all uploads (or you can choose to show a default area)
         results = ImageResult.query.order_by(ImageResult.upload_time.desc()).all()
    return render_template('feed.html', results=results, query_location=query_location)

@app.route('/like/<int:upload_id>')
@login_required
def like(upload_id):
    upload = ImageResult.query.get_or_404(upload_id)
    
    # Check if this user already liked the upload
    existing_like = Like.query.filter_by(user_id=current_user.id, image_result_id=upload_id).first()
    
    if existing_like:
        # Unlike: remove the existing like
        db.session.delete(existing_like)
        flash("You removed your like.")
    else:
        # Like: add a new like
        new_like = Like(user_id=current_user.id, image_result_id=upload_id)
        db.session.add(new_like)
        flash("You liked the upload!")
    
    db.session.commit()
    # Redirect back to the feed (or you can redirect to a referrer)
    return redirect(request.referrer or url_for('feed'))


@app.route('/leaderboard')
@login_required
def leaderboard():
    users = User.query.order_by(User.points.desc()).all()
    return render_template('leaderboard.html', users=users)


# History page to list all image results
@app.route('/history')
def history():
    results = ImageResult.query.order_by(ImageResult.upload_time.desc()).all()
    
    # For each result, parse the JSON into a new attribute (e.g., parsed_stats)
    for r in results:
        if r.stats_json:
            r.parsed_stats = json.loads(r.stats_json)
        else:
            r.parsed_stats = None
    
    return render_template('history.html', results=results)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)

