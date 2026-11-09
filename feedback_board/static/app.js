"use strict";

const form = document.querySelector("#feedback-form");
const submit = document.querySelector("#submit");
const refresh = document.querySelector("#refresh");
const formStatus = document.querySelector("#form-status");
const listStatus = document.querySelector("#list-status");
const list = document.querySelector("#feedback-list");
const count = document.querySelector("#count");
const dateFormat = new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" });

function status(element, message, error = false) {
  element.textContent = message;
  element.classList.toggle("error", error);
}

async function request(options) {
  const response = await fetch("/api/feedback", { ...options, signal: AbortSignal.timeout(15000) });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Request failed. Please try again.");
  return data;
}

async function loadFeedback() {
  refresh.disabled = true;
  status(listStatus, "Loading feedback…");
  try {
    const data = await request();
    const items = data.items.map((feedback) => {
      const item = document.createElement("li");
      const heading = document.createElement("div");
      heading.className = "message-heading";
      const name = document.createElement("strong");
      name.textContent = feedback.name;
      const time = document.createElement("time");
      time.dateTime = feedback.created_at;
      time.textContent = dateFormat.format(new Date(feedback.created_at));
      const message = document.createElement("p");
      message.className = "message-text";
      message.textContent = feedback.message;
      heading.append(name, time);
      item.append(heading, message);
      return item;
    });
    list.replaceChildren(...items);
    count.textContent = `${data.total} ${data.total === 1 ? "message" : "messages"} · Showing latest 10`;
    status(listStatus, data.total ? "" : "No feedback yet. Be the first to leave a message.");
  } catch {
    status(listStatus, "Could not load feedback. Please try Refresh.", true);
  } finally {
    refresh.disabled = false;
  }
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const name = form.elements.name.value.trim();
  const message = form.elements.message.value.trim();
  if (!name || !message) {
    status(formStatus, "Please enter your name and a message.", true);
    return;
  }
  submit.disabled = true;
  submit.textContent = "Submitting…";
  status(formStatus, "");
  try {
    await request({
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, message }),
    });
    form.reset();
    status(formStatus, "Feedback submitted.");
    await loadFeedback();
  } catch (error) {
    const message = error.name === "TimeoutError"
      ? "Request timed out. Refresh the list before submitting again."
      : error.message || "Could not submit feedback. Please try again.";
    status(formStatus, message, true);
  } finally {
    submit.disabled = false;
    submit.textContent = "Submit feedback";
  }
});

refresh.addEventListener("click", loadFeedback);
loadFeedback();
