# Beginner playbook

> **Repo copy of the "Beginner playbook" tab** of our team doc, *Fluid Mixing Team Plan — Rockwell × NVIDIA Innovation Lab* (exported Oct 13, 2026). The live doc is the source of truth: when the plan changes, update the doc and re-export this file. AI agents read this copy through GEMINI.md. Diagrams from the doc are described in one line here.

Everything here assumes nobody on the team has coded before. You never write code yourself: you give a coding agent one small, checkable job at a time, run what it gives you, and check the result with your own eyes. Each task card has the prompts to copy.

## How the mixing station works

Three tanks pour measured amounts of fluid through one shared pipe and one nozzle into each vial, so whatever the last recipe left in that pipe ends up in the next vial. That leftover is the whole problem we are solving.

*(Diagram in the online doc: fluid mixing station · 4 tanks, 1 shared path, 1 nozzle.)*

**What happens in one fill**

1. An operator queues up to three recipes in the Batch Scheduler. A recipe is just a list of mL per tank, e.g. Recipe 7 = 50 mL from T-400 (blue) + 20 mL from T-100 (clear).
2. The pumps always dispense in the same order: T-200 first, then T-400, then T-100, skipping tanks the recipe doesn't use.
3. All the fluids travel through the same mixing path and come out of the same nozzle into the vial.
4. The vial moves on to the cap/seal station, where a Teledyne camera checks its color and weight.
5. Three cameras watch along the way: `tank_level` (the tanks), `vial_fill` (the vial filling) and `cap_seal` (the finished vial). Their clocks are synced, so one moment can be followed across all three.

The system only knows tank numbers, not colors. Tanks can be refilled with a different color, so "T-200" means orange only because that is what it held during data collection.

**Why a vial comes out the wrong color**

- **Carryover (the documented problem).** Some of the previous recipe's mixture stays in the shared path after each fill. When the recipe changes, the first vial of the new batch gets a dose of the old mix. Example: Recipe 6 was orange (10 mL orange + 30 mL clear). Recipe 7 is blue. Vial 7, the first Recipe 7 vial, came out green: blue plus leftover orange. Vials 8 and 9 came out blue, because by then the old mix had been pushed out. Think of rinsing a paintbrush: the first stroke after switching paint carries a bit of the old color.
- **Nozzle buildup (our idea to test).** Drops of dye might cling to the nozzle tip and dry between fills, slowly adding color. If that happens, it should show up as slow drift, mostly on pale recipes and after long pauses. Card 5 tests it.

**Why dye mixing isn't simple addition**

- **Order doesn't change the final color, amounts do.** Once fully mixed, 20 mL blue + 50 mL clear looks the same whichever went in first. Order matters only because it decides what is left sitting in the pipe for the next recipe.
- **Pale colors are much more sensitive.** A drop of food coloring changes a glass of water a lot and a glass of grape juice barely at all. Likewise, the same leftover orange shifts a pale, clear-heavy recipe far more than a strong blue one.
- **Opposite colors are the worst case.** Orange into blue doesn't just make a darker blue; it changes the hue to green or brown, which is the most visible kind of mistake.

That is why our model counts dye amounts per color (orange share, blue share) and only then converts to the color the camera sees, instead of averaging colors directly.

**Why the current check misses it.** The Teledyne system compares each vial with a database of known colors: known color passes, unknown fails. A green vial in a blue batch might still pass if green is "known", and the check never says why a vial is off or warns before the next risky change. Our system adds all three: does it match **its** recipe, why not, and what to do before it happens.

**Station rules we must respect:** at most 80 mL per vial; at least 10 mL of any component used; at most 50 mL from T-200; never use T-300; never change recipes without the plant manager.

## What each tool is and where it fits

You work on your own laptop, with a coding agent writing the code. Two jobs are too heavy for a laptop, so they go out: simulation and training run on a rented NVIDIA GPU (Brev), and the explanations come from an NVIDIA AI model online (Cosmos). GitHub keeps everyone's code in sync.

*(Diagram in the online doc: where each tool runs · laptop, Brev, NVIDIA servers, GitHub.)*

Arrows show what travels: you send code and the digital twin to Brev and get synthetic images and a trained model back; the dashboard sends a vial image plus recipe info to Cosmos and gets a sentence back.

**Every tool in one table**

| Tool | What it is, in plain words | It's like… | What we use it for | Who touches it | Cost |
| --- | --- | --- | --- | --- | --- |
| Coding agent (Gemini; Claude Code) | An AI in your terminal that writes, runs and fixes code from English instructions | A programmer sitting next to you who types for you | Writing every script in this project | Everyone | Gemini free; Claude Code via a Claude Pro/Max plan |
| VS Code + terminal | The app where you see project files and type commands | The workshop | Running the agent and the scripts | Everyone | Free |
| GitHub | The team's shared online folder with full history | Google Drive for code, with undo | Sharing code; judges see it | Everyone | Free |
| Brev | A website that rents NVIDIA GPU computers by the hour | Renting a powerful car instead of buying one | Running Isaac Sim and training the vial model | Sim lead, model lead | Organizers' credits, \~$2–6/hour |
| Isaac Sim | NVIDIA's 3D simulator that obeys physics and renders camera images | A video-game engine for factories | Rendering thousands of labeled vial images from the twin | Sim lead (through the agent) | Runs on Brev |
| Digital twin | A 3D copy of the real fill station with cameras placed like the real ones | A detailed model kit of the line | The scene Isaac Sim renders | Sim lead | Free (provided) |
| Cosmos Reason | NVIDIA's AI that looks at images and answers questions about them in text | A factory expert you can text a photo to | Explaining why a flagged vial is off | App + Cosmos lead | Playground free on build.nvidia.com; our code runs it on a Brev L40S (\~$2/hour) |
| build.nvidia.com | NVIDIA's website where hosted AI models can be used with a free key | An app store for AI models | Where we test Cosmos prompts and get the key that downloads the Cosmos container | App + Cosmos lead (+ backup) | Free |
| DGX Spark / Dell GB10 | Desk-sized NVIDIA AI computers at UWM and MSOE | A school lab GPU | Optional: training or running Cosmos for the demo | Whoever gets access | Free; access not open yet |
| Streamlit | A Python tool that turns scripts into a simple web page | PowerPoint for live results | The operator dashboard | App + Cosmos lead | Free |

### Brev, from zero

- **What it is:** a website where you rent a computer with a powerful NVIDIA GPU. You never see the machine; you connect to it from your laptop's terminal.
- **Why we need it:** Isaac Sim and model training need a big GPU that laptops don't have.
- **How you get in:** the captain gets a sign-up link for the team's Brev organization and shares it. Each person signs up with their own account; the team shares one pot of credits.
- **What a "launchable" is:** a ready-made machine with the software already installed. We use the Isaac Sim launchable, so nobody installs Isaac Sim by hand.
- **What you'll actually do:** click Launch → wait \~10 minutes → type `brev shell <name>` in your terminal → you're now typing on the rented machine. `brev copy` moves files between it and your laptop.
- **The money rule:** a running instance spends credits every minute, even if nobody is typing. **Stop** pauses it and keeps your files. **Delete** wipes it. Stop it at the end of every session.
- **Common confusion:** Brev is not a program on your laptop (besides the small `brev` command) and not an AI. It's just the rented computer the AI and Isaac Sim run on.

### Isaac Sim, from zero

- **What it is:** NVIDIA's simulator. Give it a 3D scene and it can render realistic camera images and simulate physics.
- **Why we need it:** the organizers want us to train on simulated images, not real ones, the way a real plant would have to before a new recipe ever runs. Isaac Sim turns the digital twin into unlimited labeled training images.
- **What "headless" means here:** on Brev there's no window to look at. The coding agent runs Isaac Sim with Python scripts, and you look at the output by copying image files to your laptop.
- **What Replicator is:** the part of Isaac Sim that randomizes the scene for each image (liquid color, fill level, lighting, slight camera wobble) and saves the correct label next to every image automatically.
- **What you'll actually do:** you won't click inside Isaac Sim at all. You'll tell the agent on Brev what images you want (cards 6–7) and check the results by eye against real photos.
- **Common confusion:** Isaac Sim doesn't detect bad vials. It only makes the practice images; the vial model learns from them.

### Cosmos, from zero

- **What it is:** NVIDIA's family of AI models for the physical world. We use **Cosmos Reason**: you send it images plus a question, it answers in text. (The other kind, the generator, makes videos; we don't use it.)
- **Why we need it:** operators need to know *why* a vial is off and what to do, in plain words. Cosmos writes that sentence. It is also our clearest "Physical AI model", one of the organizers' four judging criteria.
- **Where it runs:** in two places. The browser playground on build.nvidia.com runs on NVIDIA's servers, free. For code, we run our own copy (a NIM: a ready-made container from NVIDIA) on a Brev GPU, and the script on your laptop sends requests to it through a port forward. Your laptop does no heavy work.
- **What we send it:** the vial photo, a photo of what that recipe should look like, the intended and previous recipe, the dispense order, and our color numbers. The image alone can't tell it what the vial was supposed to be (card 9 tests exactly this).
- **What it sends back:** e.g. "This vial is green instead of blue; leftover orange from the previous recipe likely mixed in. Run a clear flush before blue recipes."
- **What it does not do:** decide pass/fail (the color math and vial model do that), measure exact color, or work offline. It can also be confidently wrong, so we score how often its explanations are right.

**How it all connects for one vial:** before the fill, the flush advisor on the laptop warns about a risky recipe change → after the fill, the color check (and, if unsure, the vial model trained on Isaac Sim images) decides pass or fail → only if it fails, Cosmos explains why → the dashboard shows all three to the operator.

## Exactly what you'll do: twin, Brev, Cosmos

This is the hands-on version: which buttons, which commands, which files appear. The task cards say *what* to build; this section says *how the tools are actually used* while you build it.

### 1. Getting the digital twin and the data

Everything comes from the organizers' Google Drive. Nothing needs to be requested.

| What | Link | Who needs it | Where it goes |
| --- | --- | --- | --- |
| Fluid Mixing dataset (real images, videos, labels) | [Fluid Mixing Station dataset](https://drive.google.com/drive/folders/1qwV2BEz3ODX17kwNCr9M15DfkY8U_blQ?usp=sharing) | Everyone | `data/` in the repo folder on each laptop (Git ignores it) |
| Digital twin for datasets 1 and 2 (USD files for Isaac Sim) | [Download the digital twin](https://drive.google.com/file/d/1nXRN_VZ_DKGS33jtELwn6z8WR8dbQfKe/view?usp=sharing) | Sim lead | The Brev instance (and a backup copy on the team Drive) |
| Everything in one place | [Innovation Lab data folder](https://drive.google.com/drive/folders/1GWuHV2WUNLztq_Fga6xBH7qFzhxDaac8?usp=sharing) | Reference | — |

Ignore the FANUC robot twin (that's Dataset 3) and the Emulate3D twin on the CSI workstation (not needed for our plan).

**What the twin contains, per the organizers:** a 3D model of the fill station and cap/seal station in USD format, virtual cameras placed to match the real `vial_fill` and `cap_seal` cameras, and a script that renders images from those cameras. The tanks are **not** modeled, and the liquid color is only approximate, which is why card 7 calibrates it.

**Getting the twin onto Brev (pick one):**

1. **Via your laptop:** download the zip from the link (if Google warns it "can't scan for viruses", that's normal for big files; click Download anyway). Then from your laptop's terminal: `brev copy ~/Downloads/<twin-file>.zip <instance-name>:/home/ubuntu`
2. **Straight onto Brev (faster on slow home Wi-Fi):** inside `brev shell`, ask the agent: *"Install gdown and download the public Google Drive file with ID 1nXRN\_VZ\_DKGS33jtELwn6z8WR8dbQfKe into /home/ubuntu/project, then unzip it and list what's inside."* (The ID is the long code in the link.)

Then, on Brev: *"Explain in plain English what each file and folder in the twin is for, which file is the main scene, and how the render script is meant to be run."* Save that answer in RUNBOOK.md: it's your map of the twin.

Never put the twin or the dataset in GitHub: they're too big and not ours to republish.

### 2. A Brev session, screen by screen

**Once, before the first session (sim lead and model lead):**

- **Mac:** in Terminal, `brew install brevdev/homebrew-brev/brev` (install [Homebrew](https://brew.sh/) first if `brew` isn't found), then `brev login`.
- **Windows:** the Brev command runs inside WSL (a Linux window on Windows). Open PowerShell as administrator, run `wsl --install`, restart, finish the Ubuntu setup it opens, then in that Ubuntu window run the Linux install line from [Brev's CLI docs](https://docs.nvidia.com/brev/latest/brev-cli.html) and `brev login`. If this gets painful, let a teammate with a Mac be the sim lead.
- `brev login` opens the browser; sign in with the account that joined the team's Brev organization.

**Every session:**

1. **Open [brev.nvidia.com](https://brev.nvidia.com/) and sign in.** Check the organization name at the top is your team's, so you spend team credits, not your own.
2. **Click Compute.**
   - First time ever: open the [Isaac Sim launchable](https://brev.nvidia.com/launchable/deploy/now?launchableID=env-35JP2ywERLgqtD0b0MIeK1HnF46), pick **RTX PRO 6000** (else L40S), an **AWS** option, and one that shows **Start/Stop**. Give it a simple name like `fluid-isaac`. Deploy.
   - Every later time: your instance is listed as Stopped. Click **Start**.
3. **Wait for "Running".** About 10 minutes the first time, a few minutes after that. The page may not refresh by itself; reload Compute.
4. **Connect from your laptop terminal:** `brev ls` (shows your instance and its status), then `brev shell fluid-isaac`. The prompt changes to something like `ubuntu@...`: you are now typing on the rented computer.
5. **First time only, set up the instance:** install the coding agent (`curl -fsSL https://antigravity.google/cli/install.sh | bash`, then `agy`; open the sign-in link it prints on your laptop). Make a project folder: `mkdir -p ~/project`.
6. **Bring your latest files over.** On your laptop, zip the `scripts/` folder plus GEMINI.md, then in a **second** laptop terminal: `brev copy scripts.zip fluid-isaac:/home/ubuntu/project`. Back in the Brev terminal: `cd ~/project && unzip -o scripts.zip`.
7. **Start a session that survives disconnects:** `tmux new -s work` (if it says not found, ask the agent to install tmux). Long renders keep running inside tmux even if your laptop sleeps. To leave it running: press Ctrl+B, then D. To come back later: `tmux attach -t work`.
8. **Run the agent and do the card:** `agy`, then the card's prompts (cards 6–8).
9. **Bring results home.** Ask the agent to zip the outputs, then in your second laptop terminal: `brev copy fluid-isaac:/home/ubuntu/project/outputs.zip ~/Downloads`. Look at them on your laptop.
10. **Commit from your laptop,** not from Brev: copy any new or changed scripts into the repo folder and ask your laptop agent to commit. Big outputs go to the team Drive, not GitHub.
11. **Log it:** in the team credit sheet, write date, GPU type, hours running, hourly rate shown in Brev, and what you did.
12. **Stop the instance:** Compute → **Stop** (or `brev stop fluid-isaac`). Wait until it says **Stopped**. Never Delete unless the team agrees you're done with it.

Rule of thumb: if you're thinking, planning or reading, do it on your laptop with Brev stopped. Brev should only be Running while something is rendering or training.

### 3. What runs on Brev, file by file

This is the folder you'll end up with on the instance. You don't create it by hand: the agent builds it as you work through cards 6–8.

| File or folder | Made in | What it is | What you check |
| --- | --- | --- | --- |
| `project/twin/` | Section 1 | The unzipped digital twin | Agent's plain-English map of it is in RUNBOOK.md |
| `scripts/render_test.py` | Card 6 | Renders 10 images from the twin's vial\_fill camera | Same angle and vial position as a real frame |
| `scripts/set_liquid.py` | Card 7 | Sets the vial's liquid color (from orange share, blue share) and fill height | Changing the numbers visibly changes the render |
| `scripts/calibrate_colors.py` | Card 7 | Renders the 10 recipes and compares them with real clean vials | Every recipe within ΔE 3 of real |
| `scripts/generate_dataset.py` | Card 7 | Replicator script that randomizes color, fill, lighting, glare, camera wobble | A grid of 30 renders looks believable next to real crops |
| `synthetic/batch_000/ … batch_009/` | Card 7 | 2,000 images in batches of 200, each batch with a `labels.csv` (orange share, blue share, fill mL, predicted Lab) | Labels match what you see in a few random images |
| `scripts/train_vial_model.py` | Card 8 | Trains the small vial model on `synthetic/` | Training log shows the error going down |
| `models/vial_model.pt` | Card 8 | The trained model file | Copied to the laptop and the team Drive |
| `outputs/` | All | Logs, grids, tables to bring home | Zipped and copied at the end of each session |

The trained model is small, so the testing on real vials (card 8's second prompt) and everything after it can run on a laptop. Brev is only for rendering and training.

### Recording runtime and cost (the organizers asked for this)

The compute guide asks every team to record the GPU, runtime and approximate credits for each run, so organizers can compare real performance and cost across GPUs. It also feeds your results slide ("GPU hours used") and the weekly usage update promised in the team plan.

**Two things to measure separately:**

- **Instance time:** how long the Brev machine was Running, start to stop. This is what you pay for.
- **Job time:** how long one render or training run actually took. This is what compares GPUs fairly.

The gap between them is idle time. Keep it small.

**Step 1: make every script time itself (once).** On Brev, ask the agent:

> "Add timing to every render and training script: at the start, print and save the GPU name from nvidia-smi and the start time; at the end, save the end time, total job minutes, and how much was produced (images rendered or training epochs). Append one line per run to outputs/run\_log.csv."

Then every run logs itself, and you just copy run\_log.csv home with the other outputs.

**Step 2: log each Brev session (10 seconds).** Whoever runs the session adds a row to the log below before stopping the instance. The hourly rate is shown in Brev when you choose or start the instance; write down what it says, since the planning rates may change.

| Date | Who | Instance | GPU | Started | Stopped | Instance hours | Rate ($/h) | Est. cost ($) | Job | Job minutes | Output | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-10-16 (example) | Sim lead | fluid-isaac | RTX PRO 6000 | 18:00 | 19:30 | 1.5 | \[from Brev\] | hours × rate | Card 6 test render | 4 | 10 images | First setup, mostly installing |

Est. cost = instance hours × rate. Add a final line each week with the running total.

**Step 3: do one fair benchmark early.** The first time each GPU type is used, run the same small job and record it, e.g. "render 200 images" and "train for 5 epochs". If the team ever uses both an RTX PRO 6000 and an L40S, run the same benchmark on both. That gives the organizers the comparison they asked for and tells you which is cheaper per image.

**Step 4: check against Brev's own numbers weekly.** The captain checks the credits remaining in the Brev console once a week and compares the drop with the log's total. A big gap usually means an instance was left running. Then post one line in #compute-questions or to the organizers: credits used so far, GPU hours, and what's next.

**What goes in the final submission:** total instance hours and credits, job time per 1,000 synthetic images and per training run, GPU type, and one sentence on whether the RTX PRO 6000 was worth it for each job.

### 4. Cosmos Reason, from playground to code

**Step 1: try it in the browser, no code (everyone can do this, 15 minutes).**

1. Open the [Cosmos 3 Nano Reasoner page](https://build.nvidia.com/nvidia/cosmos3-nano-reasoner) and sign in. The **Experience** tab is the playground.
2. Under **Input**, upload one file from the dataset: an image (`.jpg`, `.jpeg`, `.png`) or a short video (`.mp4`). Start with the real `vial_fill` frame of vial 7 (the green one).
3. Paste this as the **User Prompt** (the box holds up to 4,000 characters): "This vial should be Recipe 7: 50 mL blue + 20 mL clear, so it should look blue. The previous recipe was orange (10 mL orange + 30 mL clear). The pumps dispense orange, then blue, then clear through one shared pipe. Does this vial match its recipe? If not, give the most likely cause and what the operator should do, in 2 sentences."
4. To see how it reasons, add NVIDIA's reasoning instruction (below) to the end of the prompt. Leave the **System Prompt** as it is for now; step 4 changes it.
5. Click **Run**. **Preview** shows the answer, the green **Reasoning Complete** button opens its reasoning, and **JSON** shows the raw response that our code will receive.
6. Run the same image with no recipe info and compare. That's the A/B/C experiment in miniature. Then try one `tank_level` frame: "Left to right these are tanks T-100, T-200, T-300, T-400. What color liquid is in each, and is any nearly empty?" Also try a short clip from a video: Cosmos understands motion, not just still frames.
7. Paste the answers into RUNBOOK.md. If Cosmos can't see the difference in the playground, it won't in code either, and you've learned that for free.

```text
Answer the question using the following format:

<think>
Your reasoning.
</think>

Write your final answer immediately after the </think> tag.
```

The playground compares one vial at a time. Comparing a vial with a clean reference vial in one request is done in code (step 3), which accepts several images.

**Step 2: start our own Cosmos on Brev (App + Cosmos lead, about 30 minutes the first time).**

The Cosmos 3 page has no Python example any more. Its **Deploy** tab shows how to run Cosmos yourself as a **NIM**: a ready-made Docker container that NVIDIA builds, which answers the same kind of requests as the playground. That is how our code reaches Cosmos. Cosmos 3 Nano needs about 17 GB of GPU memory, so it runs on a Brev GPU, not on a laptop.

1. Use the same NVIDIA API key as Day 1 step 11; it also unlocks NVIDIA's container registry.
2. In Brev, launch a GPU instance with an **L40S** (48 GB), an **AWS** option, and **Start/Stop**. Name it `fluid-cosmos`, so Cosmos can run while the sim lead renders on `fluid-isaac`.
3. `brev shell fluid-cosmos`, then run the Deploy tab's commands below (also in RUNBOOK.md). The first start downloads the model, which takes several minutes; later starts are quick because it stays cached on the instance's disk.
4. Cosmos is ready when `curl http://127.0.0.1:8000/v1/health/ready`, typed in a second Brev terminal, answers without an error. Press Ctrl+B, then D, to leave it running inside tmux.
5. On your laptop, open a new terminal and connect your laptop's port 8000 to the instance: `brev port-forward fluid-cosmos --port 8000:8000`. Leave that terminal open. Now `http://127.0.0.1:8000` on your laptop reaches Cosmos on Brev. (If that command isn't available, `ssh -L 8000:localhost:8000 fluid-cosmos` does the same.)
6. When you're done: stop the instance and log the hours, like every Brev session.

```bash
docker login nvcr.io          # Username: $oauthtoken   Password: your NVIDIA API key
export NGC_API_KEY=<your NVIDIA API key>
export LOCAL_NIM_CACHE=~/.cache/nim
mkdir -p "$LOCAL_NIM_CACHE"
chmod -R a+w "$LOCAL_NIM_CACHE"
tmux new -s cosmos
docker run -it --rm \
    --gpus all \
    --ipc host \
    --shm-size=32GB \
    -e NGC_API_KEY \
    -v "$LOCAL_NIM_CACHE:/opt/nim/.cache" \
    -u $(id -u) \
    -p 8000:8000 \
    nvcr.io/nim/nvidia/cosmos3-reasoner:latest
```

**Step 3: call it from Python with `scripts/ask_cosmos.py` (already in the repo).**

This script is NVIDIA's official cookbook example turned into one command. It packs your images (or one `.mp4`) into the request, media first and question last, uses NVIDIA's recommended settings, and with `--think` splits the reasoning from the answer. With the port forward from step 2 open, run on your laptop:

```powershell
python scripts/ask_cosmos.py data/csi-vial-fill-dataset/vial_fill/images/<vial 7 frame>.jpg data/csi-vial-fill-dataset/vial_fill/images/<vial 9 frame>.jpg --prompt "Image 1 should be Recipe 7 (50 mL blue + 20 mL clear). Image 2 is a correct Recipe 7 vial. The previous recipe was orange. Does image 1 match its recipe? If not, give the most likely cause and the operator's next step, in 2 sentences." --think
```

You should see `Asking nvidia/cosmos3-nano-reasoner at http://127.0.0.1:8000/v1 ...`, then `--- Cosmos reasoning ---` and `--- Cosmos answer ---`. The answers should look like the playground's. "Could not reach Cosmos" means the container or the port forward isn't running.

The heart of the script, if you want to see exactly what is sent:

```python
import base64
from pathlib import Path
import openai

def as_data_uri(path):
    # The Cosmos server can't see our disk, so we send the image's bytes inside the request
    return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")

# Our Cosmos NIM on Brev, reached through the port forward. A local NIM ignores the key.
client = openai.OpenAI(api_key="not-used", base_url="http://127.0.0.1:8000/v1")

response = client.chat.completions.create(
    model="nvidia/cosmos3-nano-reasoner",
    messages=[
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": as_data_uri("vial7.jpg")}},  # images first
            {"type": "text", "text": "What color is the liquid in this vial?"},     # question last
        ]},
    ],
    max_tokens=4096,
)
print(response.choices[0].message.content)
```

Card 9 builds `scripts/explain.py` on top of `ask_cosmos.py`. If the organizers announce a hosted Cosmos 3 endpoint, put its address in `.env` as `COSMOS_BASE_URL` (and the key as `NVIDIA_API_KEY`); nothing else changes.

**Step 4: make the answer usable by the dashboard.** Ask Cosmos to answer in a fixed format, so code can read it:

> System prompt: "You inspect vials on a color-mixing line. Answer only in JSON with keys: matches\_recipe (true/false), observed\_color, likely\_cause, operator\_action, confidence (low/medium/high)."

A typical answer then looks like: `{"matches_recipe": false, "observed_color": "green", "likely_cause": "leftover orange from the previous recipe", "operator_action": "expect the next vials to clear; flush with clear before blue recipes", "confidence": "medium"}`. The dashboard shows `likely_cause` and `operator_action` in its third panel.

**Step 5: wire it in safely.**

- The dashboard calls `explain.py` **only** for flagged vials (the cascade).
- Every answer is saved in `outputs/explanations_cache.json`, keyed by the recipe change, e.g. `"6->7"`. A repeat of the same change reuses the saved answer, so the demo still works if the internet drops or the Cosmos instance is stopped.
- Every request and answer is also appended to `outputs/cosmos_log.csv`. That log is your evidence for explanation accuracy in the results table.
- If Cosmos errors or times out, the dashboard shows "explanation unavailable" and still shows the pass/fail decision. Detection never depends on Cosmos.

## Words you'll hear

| Word | What it means for us |
| --- | --- |
| Terminal | The text window where you type commands. On Windows: PowerShell; on Mac: Terminal. In VS Code: menu Terminal → New Terminal. |
| Coding agent | An AI (Gemini, or Claude Code) that runs in the terminal, writes code files, runs them and fixes errors. You talk to it in English. |
| Python | The programming language the agent will write almost everything in. |
| Script | One code file that does one job, e.g. `extract_frames.py`. You run it with `python extract_frames.py`. |
| Repo / GitHub | The team's shared project folder online. Everyone's work goes there. |
| Commit / push | Commit = save a snapshot of your changes. Push = upload those snapshots to GitHub. Pull = download teammates' latest work. |
| Package / `pip install` | Ready-made code libraries (e.g. OpenCV for images). The agent installs them for you. |
| Virtual environment (venv) | A private box of packages for this project so nothing on your laptop breaks. Ask the agent to make one. |
| GPU | The graphics chip that makes simulation and AI training fast. We rent one on Brev. |
| Instance | A rented computer on Brev. Running = costs money. Stopped = paused, almost free. |
| SSH / `brev shell` | Logging into the rented computer from your terminal. |
| Headless | No screen or windows; you see results by copying image or video files back to your laptop. |
| USD | The 3D file format of the digital twin. Isaac Sim opens it. |
| Render | Making an image of the 3D twin from a virtual camera. |
| Synthetic data | Images made by the twin, with labels that come for free. Our training data. |
| Model / training / inference | Model = a program that learned from examples. Training = the learning. Inference = using it on new images. |
| API key | A password that lets your code use an online AI (e.g. Cosmos on build.nvidia.com). Never share it or commit it. |
| `.env` file | A local file that holds API keys, kept out of GitHub. |
| CIELAB / ΔE | A way to measure color like the eye sees it. ΔE is the distance between two colors; about 2 is the smallest difference people notice. |
| Leave-one-recipe-out | Testing method: hide one recipe, build with the other nine, test on the hidden one, repeat for all ten. Proves it works on recipes it has not seen. |
| Baseline | The simplest working method. Everything fancier must beat its score. |

## Day 1: set up your laptop (everyone, about 1 hour)

Do these in order. If any step fails, copy the exact error text and ask in the team chat or paste it to the agent once step 6 works.

1. **Install VS Code** from [code.visualstudio.com](https://code.visualstudio.com/). This is where you'll see files and run the terminal.
2. **Install Git** from [git-scm.com/downloads](https://git-scm.com/downloads) (Windows: accept the defaults). Mac: open Terminal, type `git --version`, and accept the prompt to install developer tools.
3. **Install Python 3.12** from [python.org/downloads](https://www.python.org/downloads/). Windows: tick **"Add python.exe to PATH"** on the first screen. Check in a new terminal: `python --version` (Mac: `python3 --version`).
4. **Get the team repo.** Accept the GitHub invite from the event dashboard. In VS Code: Source Control icon (left bar) → **Clone Repository** → sign in to GitHub → pick the team repo → choose a folder like Documents.
5. **Open the terminal** in VS Code: menu **Terminal → New Terminal**. It opens inside the repo folder.
6. **Install the coding agent:** Windows PowerShell: `irm https://antigravity.google/cli/install.ps1 | iex` · Mac: `curl -fsSL https://antigravity.google/cli/install.sh | bash`. Close and reopen the terminal, type `agy`, and sign in with your Google account in the browser.
7. **First prompt, to set up the project safely** (copy it whole):

   > "I have no coding experience; explain each step simply. In this folder: (1) create a .gitignore that ignores data/, outputs/, .venv/, .env, \*.mp4, \*.zip and model files; (2) create a Python virtual environment in .venv and install everything listed in requirements.txt; (3) tell me the exact command to activate the environment on my computer."
8. **Second prompt, the project memory file (already done: GEMINI.md and CLAUDE.md are in the repo, so just pull; kept here for reference):**

   > "Create GEMINI.md describing our project: Rockwell × NVIDIA Innovation Lab, Dataset 2 Fluid Mixing. Goal: predict risky recipe changes, check each vial's color against its recipe, explain the cause. Rules: real images are for testing only, never training; never commit data or API keys; keep scripts small, one job each, in scripts/; explain everything simply because the team has no coding experience."
9. **Get the data:** download the [Fluid Mixing dataset](https://drive.google.com/drive/folders/1qwV2BEz3ODX17kwNCr9M15DfkY8U_blQ?usp=sharing) into a `data/` folder inside the repo. Because of step 7, Git ignores it, so it never uploads.
10. **API key:** only the Cosmos lead (plus an optional backup) does this; everyone else skips it. Create a free key at [build.nvidia.com](https://build.nvidia.com/settings/api-keys). Ask the agent: *"Create an empty .env file with a line NVIDIA\_API\_KEY="*, then paste your key after the = yourself. Never paste a key into chat or Slack.
11. **Save and share:** ask the agent *"Commit and push the .gitignore and GEMINI.md with a clear message."* Teammates then click **Sync** in VS Code to get them.

Done when: `agy` answers you, the data opens, and GEMINI.md is on GitHub. One person does steps 8 and 11. Everyone else pulls first, then runs step 7 on their own laptop, because the environment and .env stay local and never upload.

## The work loop (every session)

1. **Pull first.** VS Code → Source Control → **Sync**, so you have teammates' latest work.
2. **Activate the environment** with the command the agent gave you on Day 1, then start `agy`.
3. **Say what you're doing today in one sentence,** pointing at the task card: *"Read GEMINI.md. Today I'm doing task card 3 from our playbook: the baseline color check."*
4. **Ask for one small piece.** Good: *"Write scripts/crop\_vial.py that crops the vial from one frame and saves the crop to outputs/crops/."* Bad: *"Build the whole system."*
5. **Before running, ask:** *"In plain English, what will this do, what command runs it, and what should I see if it worked?"*
6. **Run it and check with your eyes.** Open the image, read the numbers, compare with what the agent said you should see. This is your real job.
7. **If it fails,** paste the whole error plus one line on what you expected. If the same error comes back three times: start a fresh session, or hand that one problem to Claude Code.
8. **When it works, save it:** *"Commit this with a clear message and push."* Small saves mean you can always undo.
9. **Write it down:** *"Add the command that worked and what it does to RUNBOOK.md."*
10. **Before you stop:** stop any Brev instance, then post one line in team chat: what works now, what's next, any blocker.

**Prompts that help beginners**

- *"Explain this like I've never coded. What does each part do?"* (Do this for anything you'll present.)
- *"Show me the result as a picture or a simple table, not just numbers."*
- *"Is there a simpler way to do this?"*
- *"What could make this result wrong or misleading?"*
- *"Make a 3-sentence summary of what we built today that I can paste into our one-pager notes."*

Two rules: never let two people edit the same script at the same time (claim it in chat first), and never accept a number you can't explain.

## Using Gemini and Claude together

We use two coding agents only: Gemini and Claude Code (we no longer use Codex or GPT-6 Astra). Gemini does the everyday building for free; Claude Code is the specialist you bring in for hard problems and second opinions. Both work on the same files in the same repo and read the same rules: Gemini reads GEMINI.md, and Claude Code reads CLAUDE.md, which pulls in GEMINI.md. So handing work from one to the other is just a matter of leaving good notes.

**One-time setup for Claude Code (only the people with a Claude plan)**

1. Install Claude Code. Windows PowerShell: `irm https://claude.ai/install.ps1 | iex` · Mac: `curl -fsSL https://claude.ai/install.sh | bash`. Close and reopen the terminal.
2. In the repo folder, run `claude` and sign in with your Claude account (Pro or Max).
3. Check it loaded our rules: ask "What are our project rules, and what have we finished so far?" It should answer from GEMINI.md and docs/PROGRESS.md: real images are for testing only, never commit data or keys, small scripts in scripts/, Cards 1 and 2 done. There is nothing to copy: editing GEMINI.md updates both agents.
4. On a Brev instance, install it with the Mac line; over SSH it prints a sign-in link to open on your laptop.

**Who does what by default**

| Job | Default agent | Why |
| --- | --- | --- |
| Data exploration, baseline, flush model, dashboard, Cosmos script, docs | Gemini | Free, and the organizers say Gemini 3.7 Flash solved every problem in their tests |
| Isaac Sim scripts on Brev, Replicator randomization, color calibration | Gemini first, Claude when stuck | Headless simulation is the hardest, least familiar part |
| "Why don't synthetic results transfer to real vials?" | Claude | Needs careful reasoning across many files |
| Final check before the live test and before submission | Claude reviews | A second model catches mistakes a beginner can't see |

**Three ways to combine them**

1. **Escalation (use always).** Gemini builds. If the same error survives three attempts, commit what you have, ask Gemini to write a handoff note, and give that note to Claude. When Claude fixes it, switch back to Gemini.
2. **Builder + reviewer (use on anything that produces a number for judges).** Gemini writes the script; Claude reviews it without rewriting it. This costs only a few Claude messages and protects your results table.
3. **Planner + doer (use for cards 7, 8 and 10).** Claude writes a short step-by-step plan into PLAN.md; Gemini carries out one step per prompt. Planning takes a handful of Claude messages; the long, message-hungry work happens on the free agent.

Claude Pro has rolling usage limits, so spend it on these three uses, not on routine tasks. The sim lead's Max plan, if granted, has several times more room for the Isaac Sim work.

**Rules that keep two agents from fighting**

- Only one agent works on a task at a time. Never run Gemini and Claude on the same files at once.
- Commit before every switch, so either agent's changes can be undone.
- Each handoff goes through files (HANDOFF.md, PLAN.md, REVIEW.md), not your memory of the last chat. A fresh agent knows only what's written down.
- If the two agents disagree, ask each to explain its reasoning in plain English, then run the test that settles it. Don't pick the answer that sounds more confident.

The exact handoff, review and planning prompts are in "Every prompt in one list" at the end of this tab.

## Week 1 task cards (Oct 12–18): data, baseline, flush model

Captain, this week (no code): submit the team plan by Oct 14; in #dataset-2-fluid-mixing ask whether the tanks hold dissolved dyes or pigments, and what a scrapped vial and a flush cost; in #data-and-testbed-requests tag Shamar Webster to request the extra recorded run and a live-test slot in Oct 28–30.

### Card 1 · Explore the data

**Who:** Model lead, everyone watching. **Goal:** know exactly what files we have.

> "Look through data/ and give me a plain-English inventory: folders, number of images and videos per camera, what the label files contain, with 3 example rows. Don't change anything."

> "Write scripts/show\_examples.py that saves a contact sheet (a grid image) of 12 vial\_fill frames to outputs/, labeled with recipe ID and timestamp."

**Check:** open the contact sheet. Can you see filled vials and read the recipe IDs? **Done when:** the inventory is saved in RUNBOOK.md and everyone has looked at the sheet.

**Status: done (Oct 13).** The inventory is in RUNBOOK.md and the contact sheet comes from `scripts/show_examples.py`. What we learned and why it matters: `docs/PROGRESS.md`.

### Card 2 · Line up the three cameras

**Who:** Model lead. **Goal:** for any moment, find the matching vial\_fill, tank\_level and cap\_seal frames.

> "Using the timestamps in the file names, write scripts/align\_cameras.py that, for each labeled vial's fill end time, finds the nearest frame from each of the 3 cameras and saves a CSV in outputs/ with the three file names and the time gap to each."

> "Make a histogram of the time gaps and list any vials where a camera has no frame within 2 seconds."

**Check:** open 3 random rows' images side by side; do they show the same moment? **Done when:** the CSV exists and missing frames or clock offsets are written in RUNBOOK.md.

**Status: scripts done (Oct 13).** `scripts/align_cameras.py` builds the table and `scripts/plot_time_gaps.py` draws the histogram for all three cameras and lists any vial with a camera gap over 2 seconds. Still to do: write the gaps it finds (and any missing frames) into RUNBOOK.md and docs/PROGRESS.md, and do the by-eye check of 3 random rows.

### Card 3 · Baseline color check

**Who:** Model lead. **Goal:** the simplest working vial checker and its score: the number to beat.

> "Write scripts/crop\_vial.py: the camera is fixed, so help me pick one rectangle around the vial. Show me a frame with the rectangle drawn so I can confirm it."

> "For each labeled vial, take the frame just after its fill end time, crop it, and compute the average color in CIELAB. Save a CSV with vial number, recipe, position in batch (1st/2nd/3rd) and L, a, b."

> "Each recipe's 3rd vial is its clean reference color. Using leave-one-recipe-out, flag a vial as off-recipe when its ΔE2000 to its recipe's reference is above a threshold. Report how many off-color first vials it caught, how many false alarms it raised, and draw a chart of ΔE for every vial colored by batch position."

**Check:** in the chart, are first vials after a color change clearly higher? Is vial 7 (Recipe 7) flagged? **Done when:** the baseline score is in the results table and you can explain the chart in two sentences.

### Card 4 · Fit the flush model

**Who:** App + Cosmos lead. **Goal:** the formula from module 1 working on real data.

> "Read the module 1 formula I'll paste. Step 1: build the map g. For the 10 recipes, compute each recipe's orange share and blue share from the label file's tank volumes, and pair them with the clean 3rd-vial Lab colors from outputs/. Fit a smooth map from (orange share, blue share) to Lab, then show me predicted vs real color for each recipe as colored squares side by side."

> "Step 2: for each recipe change in the labels, predict the first vial's color using the residue volume V\_r as an unknown. Find the V\_r value that best matches the real first vials. Tell me the value in mL and the prediction error for each transition."

> "Step 3: write scripts/flush\_advisor.py that takes a queue of recipe IDs and prints, for each change, predicted ΔE, the light (green <2, amber 2–5, red >5) and whether a clear flush or a reorder would fix it."

**Check:** run the advisor on Recipe 6 → 7. It must come out red. Run Recipe 7 → 7: it must be green. **Done when:** V\_r is fitted and the advisor runs on any queue.

### Card 5 · Test the nozzle hypothesis

**Who:** App + Cosmos lead, or captain. **Goal:** decide with data whether nozzle buildup matters.

> "Using the five videos, find every completed fill (videos 1–4 are unlabeled; detect fills from the vial\_fill camera and label each vial's color). Plot color error against the number of fills since the last recipe change and against idle time before the fill, pale recipes and dark recipes separately."

**Check:** is there a clear upward trend, mainly on pale recipes? **Done when:** you write one of two sentences in RUNBOOK.md: "Drift found: X ΔE per Y fills" (then ask the agent to add the nozzle term n), or "No measurable drift; nozzle term left at 0".

### Card 5b · Read the tank colors

**Who:** App + Cosmos lead (or captain). **Goal:** know which dye is in each tank from the `tank_level` camera, so expected vial colors update automatically when a tank is refilled with a different color. The control system only knows tank numbers, never colors.

> "Show me 6 tank\_level frames from different times. Help me draw one fixed box over the liquid in each of T-100, T-200 and T-400 (skip T-300, it's out of service) and show the boxes drawn on a frame so I can confirm them."

> "Measure the average Lab color inside each box for every tank\_level frame and plot each tank's color over time. Mark any time a tank's color changes noticeably."

> "Write scripts/tank\_reader.py: for one tank\_level frame, output each tank's dye (clear, orange, blue, other, or unsure) and a rough fill level, using the color measurement. Only when the result is 'unsure', ask Cosmos with explain.py: 'Left to right these are tanks T-100 to T-400. What color liquid is in each, and is any nearly empty? Answer in JSON.'"

> "Connect tank\_reader.py to flush\_advisor.py: each recipe's expected color should use the dye actually seen in each tank, and print a warning when a tank no longer holds what the recipes assume. Run the reader at the start of each batch, not on every vial."

> "To test a tank change without touching the line, make a copy of one tank\_level frame with T-200's liquid digitally recolored to green, and show me what tank\_reader.py and flush\_advisor.py say."

**Check:** on the recorded data it should say T-100 clear, T-200 orange, T-400 blue. On the recolored test frame it should warn that T-200 changed. Watch out: liquid in a big tank looks darker than the same liquid in a thin vial, so use the reader to identify **which dye** is in each tank and keep the calibrated map g for predicting vial colors. Clear diluent behind a translucent wall may be hard to read; that's what the "unsure" path is for.

**Rules:** read the existing footage only; never move or re-aim a camera; never refill or change tanks yourselves (a real tank-change test happens only if CSI does it while you watch). The twin has no tanks, so this part uses color math and Cosmos without training. Ask the organizers before using real tank images as examples inside Cosmos prompts.

**Done when:** tank\_reader.py feeds the flush advisor, and the recolored test frame triggers a warning.

## Week 2 task cards (Oct 15–25): synthetic data, vial model, Cosmos

### Card 6 · First Brev session and twin render

**Who:** Sim lead (start as soon as the Brev link arrives). **Goal:** one image from the twin's vial\_fill camera on your laptop, for under \~$12.

Follow "Setup, step B" in the Team plan tab, or the more detailed "A Brev session, screen by screen" near the top of this tab (steps 1–8); get the twin onto Brev as in "Getting the digital twin"; then on the instance:

> "I have no coding experience. This is a headless Isaac Sim machine. Unzip the digital twin in /home/ubuntu, find the vial\_fill camera and the render script that came with it, and render 10 images to /home/ubuntu/renders. Explain each step and tell me the exact brev copy command to bring the images to my laptop."

**Check:** put a render next to a real vial\_fill frame. Same angle, same vial position? **Done when:** the render is on your laptop, the instance is **stopped**, and GPU type + hours + credits are logged in the team's credit sheet.

### Card 7 · Calibrated synthetic dataset

**Who:** Sim lead. **Goal:** 2,000+ labeled twin images whose colors match the real camera.

> "Make the liquid in the twin's vial controllable from a script: its color (from an orange share and a blue share) and its fill height (10–80 mL). Use the color map g from scripts/flush\_advisor.py \[copy the file to the instance first\]. Render the 10 recipes' clean colors and save them with their recipe IDs."

> "Compare each rendered recipe color with the real clean 3rd-vial color in Lab. Adjust the twin's liquid material until every recipe is within ΔE 3, and show me the before/after table."

> "Using Replicator, generate 2,000 images: random orange/blue shares including contaminated mixes, random fill level, small random lighting changes, glare, and 1–2 pixel camera jitter. Save each image with a labels CSV: orange share, blue share, fill mL, predicted Lab. Save in batches of 200 so a crash loses little."

**Check:** look at a grid of 30 random synthetic images next to real ones. Would a stranger believe they come from the same camera? **Done when:** the dataset is copied off the instance (not to GitHub; to the team Drive) and the calibration table is in RUNBOOK.md.

### Card 8 · Train the vial model on twin data, test on real

**Who:** Model lead. **Goal:** a model that beats the baseline on real vials without ever training on real images.

> "Train a small model (start with a ResNet-18 or a simple color regressor) on the synthetic images to predict orange share, blue share and fill level from the vial crop. Use our Brev L40S. Print progress in plain language and save the model to outputs/."

> "Now test on the 30 real labeled vials only: predict their color, compute ΔE to the recipe reference, and fill in a table comparing (a) the baseline, (b) synthetic-trained, (c) synthetic-trained plus the 30 real vials used as reference examples. Show caught first vials, false alarms and misses separately."

**Check:** is (b) or (c) better than the baseline? If not, ask: *"What's the most likely reason the synthetic images don't transfer to real ones?"* (usually color calibration or lighting). **Done when:** the comparison table is in the results doc.

### Card 9 · Cosmos explanations

**Who:** App + Cosmos lead. **Goal:** a plain-language cause for each flagged vial.

> "Start from scripts/ask\_cosmos.py, our working Cosmos example (playbook section 4). Write scripts/explain.py that reuses it and sends: the flagged vial crop, the clean reference image of its intended recipe, the previous recipe, the dispense order and the flush advisor's prediction. Ask Cosmos to say whether the vial matches its recipe and the most likely cause, in 2 sentences an operator understands."

> "Add two worked examples to the prompt: one clean vial and the Recipe 6 → 7 green vial with its correct explanation. Don't include the recipe being tested as an example."

> "Run it on every first vial after a recipe change, and make a table: vial, Cosmos's stated cause, the true previous recipe, and whether the cause is right."

**Experiment: does the extra context matter?** Run Cosmos three ways on the same 30 labeled vials and compare:

| Version | What Cosmos gets |
| --- | --- |
| A | Vial image only |
| B | Vial image + reference image + recipe info (intended recipe, previous recipe, dispense order) |
| C | Everything in B + our color numbers and the flush advisor's prediction |

> "Make a version of explain.py with a mode setting: A = only the vial image, B = vial image + reference image + recipe info, C = B plus our measured ΔE and the flush advisor's prediction. Run all three on the 30 labeled vials and make one table: for each version, how often Cosmos correctly said whether the vial matches its recipe, and how often it named the right cause. Use leave-one-recipe-out for the examples in the prompt."

Why: an image alone doesn't show the intended recipe or the previous one, so we expect C to win. If it does, that's hard proof our design matters, and a strong results slide. If A does surprisingly well, report that too.

**Check:** read every explanation yourself. Would an operator know what to do? **Done when:** explanation accuracy is a number in the results doc, and explanations are cached by previous → next recipe pair.

## Week 3 task cards (Oct 24–Nov 1): dashboard, live test, submission

### Card 10 · Cascade and operator dashboard

**Who:** App + Cosmos lead. **Goal:** one screen that shows the whole system working, live or on a recording.

> "Build a Streamlit app in app/ with three panels: (1) the recipe queue with a green/amber/red light per change from flush\_advisor.py and the suggested fix; (2) the latest vial crop with its verdict; (3) the Cosmos explanation when a vial is flagged. Follow the cascade: cheap color check first, the vial model only in the unsure zone, Cosmos only for flagged vials, with cached explanations."

> "Add a replay mode that plays a recorded video from data/ as if it were live, and a counter showing how many vials reached each cascade step and the average time per vial."

> "Give me one command that starts everything, and add it to RUNBOOK.md."

**Check:** run replay on video 5. Does the light turn red before vial 7 and does the explanation mention the previous orange recipe? **Done when:** a teammate who didn't build it can start the demo from RUNBOOK.md alone.

### Card 11 · Live test at CSI

**Who:** Captain organizes; whole team attends if allowed. **Goal:** recorded proof on real hardware.

Before the visit (per the organizers' data-collection guide):

- [ ] Freeze the version: *"Tag the current commit as live-test-v1 and list exactly which model files it uses."*
- [ ] Know the input: confirm with CSI whether you read the existing vial\_fill feed or bring your own camera aimed at the station (never move or re-aim their cameras).
- [ ] Prepare a trial log: *"Make a CSV template for a live trial log: time, recipe queue, predicted light, actual vial verdict, Cosmos explanation, latency, operator intervention, notes."*
- [ ] Rehearse failure: unplug the camera or kill the Wi-Fi during a replay; the app should show an error, not crash.
- [ ] Send the test plan in #data-and-testbed-requests (tag Shamar Webster) with time needed and who attends.

On site: observe first, touch nothing without the plant manager's OK, no recipe changes yourselves, log every attempt (not just good ones), and film the screen and the vials together for the video.

**Done when:** the trial log is complete and you have usable footage. Have a replay recording as backup in case the line is unavailable.

### Card 12 · Results, video, one-pager, submission

**Who:** Captain leads; everyone reviews. **Due:** Sun Nov 1, 11:59 PM CT.

> "From outputs/ and the trial log, build one results table: baseline vs our system for caught bad vials, false alarms, misses, explanation accuracy, share of vials reaching Cosmos, latency, and GPU hours/credits used. Then list honestly where it still fails."

> "Draft a one-page summary: problem, approach, results vs baseline, business case (use only the cost numbers CSI gave us), limitations, next steps. Plain English, under 450 words."

> "Write references.md crediting the datasets, the digital twin, Isaac Sim, Cosmos, every Python package we used, and the AI coding tools."

Video (\~5 min): follow the outline in the Team plan tab's "How to win" section. Record the screen with OBS Studio (free) or your OS's built-in recorder; record voice separately if the room is loud.

**Done when:** video, one-pager, repo link and references are submitted on the dashboard before the deadline. Then rehearse the finals talk twice, each person explaining their own part.

## When things go wrong

| What you see | What it usually means | What to do |
| --- | --- | --- |
| `command not found` / "is not recognized" | The program isn't installed, or the terminal was opened before installing | Close and reopen the terminal; if it persists, paste the error to the agent |
| `ModuleNotFoundError: No module named ...` | The environment isn't active, or the package isn't installed | Run the activate command from Day 1, then ask the agent to install the missing package |
| Script runs but the picture or numbers look wrong | Wrong crop, wrong frame, or wrong file | Ask: *"Show me the exact image you measured, with the crop drawn on it"* |
| The agent repeats the same fix 3 times | It's stuck in a loop | Start a fresh session with GEMINI.md and the error, or hand this one problem to Claude Code |
| Agent says it "can't access" a file | Wrong folder, or the file name has spaces | Run `pwd` (Mac) or `cd` (Windows) to see where you are; ask the agent to list the folder |
| Git says "conflict" when syncing | Two people edited the same file | Don't panic, don't force anything: ask the agent *"Explain this merge conflict and keep both people's changes"* |
| Brev launch page stuck | Normal; provisioning can take \~10 minutes | Open **Compute** in Brev; the instance appears there |
| `brev shell` can't connect | Instance is stopped or still starting | Check its status in Brev; press Start and wait a few minutes |
| Isaac Sim crashes or renders black images | Missing lights, wrong camera, or out of GPU memory | Ask the agent to render 1 image with debug output; render in smaller batches |
| Cosmos says "Could not reach Cosmos", or error 401 / 403 | The Cosmos container or the port forward isn't running; for 401/403, the key is wrong | Check .env has NVIDIA\_API\_KEY= with no spaces or quotes; make a new key if needed. For "could not reach": check the container is still running in tmux on Brev and the brev port-forward terminal is still open |
| Cosmos API error 429 | Rate limit | Wait, send fewer images, and make sure caching works |
| Credits dropping fast | An instance is running | Stop every instance you aren't actively using, now |
| Accidentally committed an API key | The key is exposed | Delete that key on build.nvidia.com immediately and make a new one; then ask the agent to remove it from Git history |

Still stuck after 30 minutes? Post in the right Slack channel: what you were trying to do, the exact error, what you tried, and when you need it fixed. Start with "BLOCKING" if the whole team is waiting on it. Compute: #compute-questions (Dan Schneider). Data or line questions: #dataset-2-fluid-mixing. CSI visits and tests: #data-and-testbed-requests (Shamar Webster).

## Every prompt in one list

Copy these in order. **\[G\]** = Gemini in Antigravity (default). **\[C\]** = Claude Code. **\[G→C\]** = start with Gemini and switch if stuck. Text in \[brackets\] is for you to fill in.

### Setup (Day 1)

1. **\[G\]** "I have no coding experience; explain each step simply. In this folder: (1) check that .gitignore ignores data/, outputs/, .venv/, .env, \*.mp4, \*.zip and model files; (2) create a Python virtual environment in .venv and install everything in requirements.txt; (3) tell me the exact command to activate the environment on my computer."
2. **\[G\]** "Read GEMINI.md and docs/PROGRESS.md, then tell me in plain English what our project is, what we've finished, and what's next." (GEMINI.md, CLAUDE.md, .gitignore, requirements.txt and .env.example are already in the repo; just pull.)
3. **\[C\]** Claude plan holders: "What are our project rules, and what have we finished so far?" (checks that CLAUDE.md loaded GEMINI.md)
4. **\[G\]** Cosmos lead only: "Copy .env.example to .env" (then paste your key after NVIDIA\_API\_KEY= yourself).
5. **\[G\]** Whenever the plan changes: "Update GEMINI.md and the matching file in docs/, then commit and push with a clear message."

### Every session (the work loop)

6. **\[G\]** "Read GEMINI.md. Today I'm doing task card \[number\] from our playbook: \[card name\]."
7. **\[G\]** "In plain English, what will this do, what command runs it, and what should I see if it worked?"
8. **\[G\]** "Here is the full error: \[paste\]. I expected \[what you expected\]. What went wrong, in simple words, and how do we fix it?"
9. **\[G\]** "Commit this with a clear message and push."
10. **\[G\]** "Add the command that worked and what it does to RUNBOOK.md."
11. **\[G\]** "Explain this like I've never coded. What does each part do?"
12. **\[G\]** "Show me the result as a picture or a simple table, not just numbers."
13. **\[G\]** "What could make this result wrong or misleading?"
14. **\[G\]** "Make a 3-sentence summary of what we built today that I can paste into our one-pager notes."

### Card 1 · Explore the data

15. **\[G\]** "Look through data/ and give me a plain-English inventory: folders, number of images and videos per camera, what the label files contain, with 3 example rows. Don't change anything."
16. **\[G\]** "Write scripts/show\_examples.py that saves a contact sheet (a grid image) of 12 vial\_fill frames to outputs/, labeled with recipe ID and timestamp."

### Card 2 · Line up the cameras

17. **\[G\]** "Using the timestamps in the file names, write scripts/align\_cameras.py that, for each labeled vial's fill end time, finds the nearest frame from each of the 3 cameras and saves a CSV in outputs/ with the three file names and the time gap to each."
18. **\[G\]** "Make a histogram of the time gaps and list any vials where a camera has no frame within 2 seconds."

### Card 3 · Baseline color check

19. **\[G\]** "Write scripts/crop\_vial.py: the camera is fixed, so help me pick one rectangle around the vial. Show me a frame with the rectangle drawn so I can confirm it."
20. **\[G\]** "For each labeled vial, take the frame just after its fill end time, crop it, and compute the average color in CIELAB. Save a CSV with vial number, recipe, position in batch (1st/2nd/3rd) and L, a, b."
21. **\[G\]** "Each recipe's 3rd vial is its clean reference color. Using leave-one-recipe-out, flag a vial as off-recipe when its ΔE2000 to its recipe's reference is above a threshold. Report how many off-color first vials it caught, how many false alarms it raised, and draw a chart of ΔE for every vial colored by batch position."
22. **\[C\]** Review the baseline (prompt 50) before you put its score in the results table.

### Card 4 · Flush model

23. **\[G\]** "Read the module 1 formula I'll paste: \[paste the formula and its bullet list from the Team plan tab\]. Step 1: build the map g. For the 10 recipes, compute each recipe's orange share and blue share from the label file's tank volumes, and pair them with the clean 3rd-vial Lab colors from outputs/. Fit a smooth map from (orange share, blue share) to Lab, then show me predicted vs real color for each recipe as colored squares side by side."
24. **\[G\]** "Step 2: for each recipe change in the labels, predict the first vial's color using the residue volume V\_r as an unknown. Find the V\_r value that best matches the real first vials. Tell me the value in mL and the prediction error for each transition."
25. **\[G\]** "Step 3: write scripts/flush\_advisor.py that takes a queue of recipe IDs and prints, for each change, predicted ΔE, the light (green <2, amber 2–5, red >5) and whether a clear flush or a reorder would fix it."
26. **\[G\]** "Run flush\_advisor.py on the queue 6, 7 and then on 7, 7, and explain both results."

### Card 5 · Nozzle hypothesis

27. **\[G\]** "Using the five videos, find every completed fill (videos 1–4 are unlabeled; detect fills from the vial\_fill camera and label each vial's color). Plot color error against the number of fills since the last recipe change and against idle time before the fill, pale recipes and dark recipes separately."
28. **\[G\]** Only if you found drift: "Add the nozzle term n to flush\_advisor.py as described in module 1, fit it on the five videos, and show me how much it improves the predictions."

### Card 5b · Tank colors

28b. **\[G\]** "Show me 6 tank\_level frames from different times. Help me draw one fixed box over the liquid in each of T-100, T-200 and T-400 (skip T-300, it's out of service) and show the boxes drawn on a frame so I can confirm them."

28c. **\[G\]** "Measure the average Lab color inside each box for every tank\_level frame and plot each tank's color over time. Mark any time a tank's color changes noticeably."

28d. **\[G\]** "Write scripts/tank\_reader.py: for one tank\_level frame, output each tank's dye (clear, orange, blue, other, or unsure) and a rough fill level, using the color measurement. Only when the result is 'unsure', ask Cosmos with explain.py: 'Left to right these are tanks T-100 to T-400. What color liquid is in each, and is any nearly empty? Answer in JSON.'"

28e. **\[G\]** "Connect tank\_reader.py to flush\_advisor.py: each recipe's expected color should use the dye actually seen in each tank, and print a warning when a tank no longer holds what the recipes assume. Run the reader at the start of each batch, not on every vial."

28f. **\[G\]** "To test a tank change without touching the line, make a copy of one tank\_level frame with T-200's liquid digitally recolored to green, and show me what tank\_reader.py and flush\_advisor.py say."

### Card 6 · First Brev session (run on the Brev instance)

29. **\[G→C\]** "I have no coding experience. This is a headless Isaac Sim machine. Unzip the digital twin in /home/ubuntu, find the vial\_fill camera and the render script that came with it, and render 10 images to /home/ubuntu/renders. Explain each step and tell me the exact brev copy command to bring the images to my laptop."

### Card 7 · Synthetic dataset (on Brev)

30. **\[C\]** Plan it first (prompt 53) with card 7 as the task.
31. **\[G→C\]** "Make the liquid in the twin's vial controllable from a script: its color (from an orange share and a blue share) and its fill height (10–80 mL). Use the color map g from scripts/flush\_advisor.py. Render the 10 recipes' clean colors and save them with their recipe IDs."
32. **\[G→C\]** "Compare each rendered recipe color with the real clean 3rd-vial color in Lab. Adjust the twin's liquid material until every recipe is within ΔE 3, and show me the before/after table."
33. **\[G→C\]** "Using Replicator, generate 2,000 images: random orange/blue shares including contaminated mixes, random fill level, small random lighting changes, glare, and 1–2 pixel camera jitter. Save each image with a labels CSV: orange share, blue share, fill mL, predicted Lab. Save in batches of 200 so a crash loses little."
34. **\[G\]** "Make a grid of 30 random synthetic images next to 30 real vial\_fill crops so I can compare them by eye."

### Card 8 · Vial model

35. **\[C\]** Plan it first (prompt 53) with card 8 as the task.
36. **\[G\]** "Train a small model (start with a ResNet-18 or a simple color regressor) on the synthetic images to predict orange share, blue share and fill level from the vial crop. Use our Brev L40S. Print progress in plain language and save the model to outputs/."
37. **\[G\]** "Now test on the 30 real labeled vials only: predict their color, compute ΔE to the recipe reference, and fill in a table comparing (a) the baseline, (b) synthetic-trained, (c) synthetic-trained plus the 30 real vials used as reference examples. Show caught first vials, false alarms and misses separately."
38. **\[C\]** If (b) and (c) don't beat the baseline: "Read GEMINI.md, the training script and the results. What is the most likely reason the synthetic images don't transfer to real ones? Rank the top 3 causes and give one quick test for each."

### Card 9 · Cosmos explanations

39. **\[G\]** "Start from scripts/ask\_cosmos.py, our working Cosmos example (playbook section 4). Write scripts/explain.py that reuses it and sends: the flagged vial crop, the clean reference image of its intended recipe, the previous recipe, the dispense order and the flush advisor's prediction. Ask Cosmos to say whether the vial matches its recipe and the most likely cause, in 2 sentences an operator understands."
40. **\[G\]** "Add two worked examples to the prompt: one clean vial and the Recipe 6 → 7 green vial with its correct explanation. Don't include the recipe being tested as an example."
41. **\[G\]** "Run it on every first vial after a recipe change, and make a table: vial, Cosmos's stated cause, the true previous recipe, and whether the cause is right. Cache explanations by previous → next recipe pair."

41b. **\[G\]** "Make a version of explain.py with a mode setting: A = only the vial image, B = vial image + reference image + recipe info, C = B plus our measured ΔE and the flush advisor's prediction. Run all three on the 30 labeled vials and make one table: for each version, how often Cosmos correctly said whether the vial matches its recipe, and how often it named the right cause. Use leave-one-recipe-out for the examples in the prompt."

### Card 10 · Dashboard and cascade

42. **\[C\]** Plan it first (prompt 53) with card 10 as the task.
43. **\[G\]** "Build a Streamlit app in app/ with three panels: (1) the recipe queue with a green/amber/red light per change from flush\_advisor.py and the suggested fix; (2) the latest vial crop with its verdict; (3) the Cosmos explanation when a vial is flagged. Follow the cascade: cheap color check first, the vial model only in the unsure zone, Cosmos only for flagged vials, with cached explanations."
44. **\[G\]** "Add a replay mode that plays a recorded video from data/ as if it were live, and a counter showing how many vials reached each cascade step and the average time per vial."
45. **\[G\]** "Give me one command that starts everything, and add it to RUNBOOK.md."

### Card 11 · Live test

46. **\[G\]** "Tag the current commit as live-test-v1 and list exactly which model files it uses."
47. **\[G\]** "Make a CSV template for a live trial log: time, recipe queue, predicted light, actual vial verdict, Cosmos explanation, latency, operator intervention, notes."
48. **\[C\]** "Read GEMINI.md and the app/ folder. We demo this on a real factory line tomorrow, run by beginners. List anything that could crash or give a wrong answer during the demo, most serious first. Don't change code; write the list to REVIEW.md."

### Card 12 · Results and submission

49. **\[G\]** "From outputs/ and the trial log, build one results table: baseline vs our system for caught bad vials, false alarms, misses, explanation accuracy, share of vials reaching Cosmos, latency, and GPU hours/credits used. Then list honestly where it still fails."
50. **\[C\]** "Review \[script name\] and the numbers it produced. Don't rewrite it. Check for mistakes that would make our results wrong: test data leaking into training, wrong frames, wrong math, a threshold tuned on the test set. Write your findings to REVIEW.md, most serious first, in plain English."
51. **\[G\]** "Draft a one-page summary: problem, approach, results vs baseline, business case (use only the cost numbers CSI gave us), limitations, next steps. Plain English, under 450 words."
52. **\[G\]** "Write references.md crediting the datasets, the digital twin, Isaac Sim, Cosmos, every Python package we used, and the AI coding tools."

### Using both agents together

53. **\[C\] Plan:** "Read GEMINI.md and task card \[number\], which I'll paste: \[paste the card\]. Write PLAN.md: 5–10 small steps, each one a single prompt I can give another coding agent, each with how I can check it worked. Don't write code yet."
54. **\[G\] Do a step:** "Read GEMINI.md and PLAN.md. Do step \[number\] only, then tell me how to check it."
55. **\[G\] Hand off:** "We've been stuck on this. Write HANDOFF.md for another AI: what we're trying to do, what you tried, the exact last error, and which files matter. Then commit."
56. **\[C\] Take over:** "Read GEMINI.md and HANDOFF.md. Fix the problem described, explain the fix in plain English, and add a short 'Resolved' note to HANDOFF.md."
57. **\[G\] Apply a review:** "Read REVIEW.md. Fix the issues one at a time, most serious first, and tell me after each fix how to check it."
58. **\[G\] or \[C\] Settle a disagreement:** "Another AI says \[paste its claim\]. Explain in plain English whether it's right, and give me one test I can run to find out."
