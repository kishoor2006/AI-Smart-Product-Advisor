import os,json,sqlite3
from pathlib import Path
from datetime import datetime
from uuid import uuid4
from flask import Flask,render_template,request,redirect,url_for,session,flash
BASE=Path(__file__).resolve().parent; DB=BASE/"database/advisor.db"; DATA=BASE/"products.json"
app=Flask(__name__); app.secret_key=os.getenv("SECRET_KEY","advisor-demo-key")
W={"budget":25,"purpose":25,"ram":15,"storage":15,"performance":10,"battery":10}
def products():
    return json.loads(DATA.read_text(encoding="utf-8"))
def product(pid): return next((p for p in products() if p["id"]==pid),None)
def init_db():
    DB.parent.mkdir(exist_ok=True)
    with sqlite3.connect(DB) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
        id INTEGER PRIMARY KEY AUTOINCREMENT,order_id TEXT UNIQUE,product_id INTEGER,product_name TEXT,
        customer_name TEXT,email TEXT,phone TEXT,address TEXT,city TEXT,state TEXT,pincode TEXT,
        quantity INTEGER,total_amount REAL,order_date TEXT,status TEXT)""")
        c.commit()
def score(p,x):
    b=max(float(x["budget"]),1); price=p["price"]
    bs=25 if price<=b else max(0,25*(1-(price-b)/b))
    ps=25 if x["purpose"] in p["purpose"] else 10
    r=int(x["ram"]); rs=15 if p["ram"]>=r else (10 if p["ram"]==r-8 else 5)
    s=int(x["storage"]); ss=15 if p["storage"]>=s else (9 if p["storage"]>=s/2 else 4)
    perf=p["performance"]/10; bat=p["battery_score"]/10
    pri=x["priority"]; bonus=(p["performance"]/100*3 if pri=="Performance" else p["battery_score"]/100*3 if pri=="Battery" else p["display_score"]/100*3 if pri=="Display" else 2)
    brand=2 if x["brand"]!="Any Brand" and p["brand"]==x["brand"] else 0
    total=min(100,bs+ps+rs+ss+perf+bat+bonus+brand)
    reasons=["Fits your selected budget" if price<=b else "Offers strong value near your budget"]
    if x["purpose"] in p["purpose"]: reasons.append("Matches your "+x["purpose"].lower()+" requirement")
    if p["ram"]>=r: reasons.append(f"Provides the requested {r} GB RAM or more")
    if p["storage"]>=s: reasons.append("Provides the requested storage or more")
    reasons.append("Strong performance for your selected priority" if pri=="Performance" else "Strong battery performance for your selected priority" if pri=="Battery" else "Good overall value for money")
    return round(total),reasons[:5]
def recommend(x):
    out=[]
    for p in products():
        q=dict(p); q["match_score"],q["reasons"]=score(p,x); out.append(q)
    out.sort(key=lambda p:(p["match_score"],p["rating"]),reverse=True)
    return out[0],out[1],sorted(out,key=lambda p:(p["price"],-p["match_score"]))[0]
@app.context_processor
def ctx(): return {"compare_count":len(session.get("compare_ids",[]))}
@app.route("/")
def home(): return render_template("index.html")
@app.route("/products")
def products_page():
    items=products(); q=request.args.get("q","").lower().strip(); brand=request.args.get("brand","All"); mx=request.args.get("max_price",""); sort=request.args.get("sort","default")
    if q: items=[p for p in items if q in p["name"].lower() or q in p["brand"].lower()]
    if brand!="All": items=[p for p in items if p["brand"]==brand]
    try:
        if mx: items=[p for p in items if p["price"]<=float(mx)]
    except: flash("Enter a valid maximum price.","error")
    if sort=="price_low": items.sort(key=lambda p:p["price"])
    elif sort=="price_high": items.sort(key=lambda p:p["price"],reverse=True)
    elif sort=="rating": items.sort(key=lambda p:p["rating"],reverse=True)
    return render_template("products.html",products=items,brands=sorted({p["brand"] for p in products()}),q=q,brand=brand,mx=mx,sort=sort)
@app.route("/product/<int:pid>")
def details(pid):
    p=product(pid)
    if not p: flash("Product not found.","error"); return redirect(url_for("products_page"))
    return render_template("product_details.html",product=p)
@app.route("/finder")
def finder(): return render_template("finder.html")
@app.route("/recommend",methods=["POST"])
def do_recommend():
    try:
        x={"budget":float(request.form["budget"]),"purpose":request.form["purpose"],"ram":request.form["ram"],"storage":request.form["storage"],"brand":request.form["brand"],"priority":request.form["priority"]}
        if x["budget"]<=0: raise ValueError
    except: flash("Please enter a valid budget.","error"); return redirect(url_for("finder"))
    a,b,c=recommend(x); session["rec"]={"x":x,"best":a["id"],"alt":b["id"],"budget":c["id"]}; return redirect(url_for("recommendation"))
@app.route("/recommendation")
def recommendation():
    r=session.get("rec")
    if not r: return redirect(url_for("finder"))
    x=r["x"]; a=product(r["best"]); b=product(r["alt"]); c=product(r["budget"])
    a["match_score"],a["reasons"]=score(a,x); b["match_score"],_=score(b,x); c["match_score"],_=score(c,x)
    return render_template("recommendation.html",best=a,alt=b,budget=c)
@app.route("/compare")
def compare():
    if request.args.get("ids"):
        try: session["compare_ids"]=[int(i) for i in request.args["ids"].split(",")][:3]
        except: pass
    ps=[product(i) for i in session.get("compare_ids",[])]; return render_template("compare.html",products=[p for p in ps if p])
@app.route("/compare/add/<int:pid>",methods=["GET","POST"])
def add_compare(pid):
    if not product(pid): return redirect(url_for("products_page"))
    ids=session.get("compare_ids",[])
    if pid not in ids:
        if len(ids)>=3: flash("You can compare up to 3 products.","error")
        else: ids.append(pid); session["compare_ids"]=ids; flash("Product added to comparison.","success")
    return redirect(request.referrer or url_for("compare"))
@app.route("/compare/remove/<int:pid>")
def remove_compare(pid):
    session["compare_ids"]=[i for i in session.get("compare_ids",[]) if i!=pid]; return redirect(url_for("compare"))
@app.route("/compare/clear")
def clear_compare(): session["compare_ids"]=[]; return redirect(url_for("compare"))
@app.route("/order/<int:pid>")
def order(pid):
    p=product(pid)
    if not p: return redirect(url_for("products_page"))
    return render_template("order.html",product=p)
@app.route("/place-order",methods=["POST"])
def place_order():
    try: pid=int(request.form["product_id"]); qty=int(request.form["quantity"]); p=product(pid)
    except: flash("Invalid product or quantity.","error"); return redirect(url_for("products_page"))
    if not p or qty<1 or qty>20: flash("Invalid quantity.","error"); return redirect(url_for("order",pid=pid))
    fields=["name","email","phone","address","city","state","pincode"]; v={f:request.form.get(f,"").strip() for f in fields}
    if not all(v.values()) or "@" not in v["email"]: flash("Please complete valid customer details.","error"); return redirect(url_for("order",pid=pid))
    oid="ASA-"+datetime.now().strftime("%Y%m%d")+"-"+uuid4().hex[:6].upper(); total=p["price"]*qty; date=datetime.now().strftime("%d-%m-%Y %I:%M %p")
    with sqlite3.connect(DB) as c:
        c.execute("INSERT INTO orders(order_id,product_id,product_name,customer_name,email,phone,address,city,state,pincode,quantity,total_amount,order_date,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (oid,pid,p["name"],v["name"],v["email"],v["phone"],v["address"],v["city"],v["state"],v["pincode"],qty,total,date,"Order Placed")); c.commit()
    return redirect(url_for("success",oid=oid))
@app.route("/order-success/<oid>")
def success(oid):
    with sqlite3.connect(DB) as c:
        c.row_factory=sqlite3.Row; o=c.execute("SELECT * FROM orders WHERE order_id=?",(oid,)).fetchone()
    if not o: return redirect(url_for("products_page"))
    return render_template("order_success.html",order=o,product=product(o["product_id"]))
@app.route("/about")
def about(): return render_template("about.html")
@app.errorhandler(404)
def notfound(e): return render_template("404.html"),404
init_db()
if __name__=="__main__": app.run(host="0.0.0.0",port=int(os.getenv("PORT",5000)),debug=True)
