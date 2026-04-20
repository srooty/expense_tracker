let transactions = JSON.parse(localStorage.getItem("transactions")) || [];

function addTransaction() {
    let desc = document.getElementById("desc").value;
    let amount = parseFloat(document.getElementById("amount").value);
    let category = document.getElementById("category").value;
    let date = document.getElementById("date").value;

    let transaction = { desc, amount, category, date };

    transactions.push(transaction);
    localStorage.setItem("transactions", JSON.stringify(transactions));

    updateUI();
}

function updateUI() {
    let list = document.getElementById("list");
    list.innerHTML = "";

    let income = 0, expense = 0;

    transactions.forEach(t => {
        let li = document.createElement("li");
        li.className = "list-group-item";

        li.innerHTML = `${t.desc} - ₹${t.amount}`;
        list.appendChild(li);

        if (t.amount > 0) income += t.amount;
        else expense += t.amount;
    });

    document.getElementById("income").innerText = "₹" + income;
    document.getElementById("expense").innerText = "₹" + Math.abs(expense);
    document.getElementById("balance").innerText = "₹" + (income + expense);
}

updateUI();