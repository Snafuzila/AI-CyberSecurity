# Lab Work 1: Cyber Threat Intelligence Mapping to Tactics and Techniques

## 👥 Group Information
* **Course:** Introduction to AI Cyber Security
* **Assignment:** Lab Work 1 - CTI Report Mapping
* **Group Members:**
  *  Lotem Kimchi 
  *  Boaz Attiya

---

## 🔗 Source CTI Report
* **Publisher:** Google Cloud Threat Intelligence (Mandiant)
* **Report Link:** [Zero-Day Exploitation of Vulnerability (CVE-2026-20245) in Cisco Catalyst SD-WAN Manager](https://cloud.google.com/blog/topics/threat-intelligence/zero-day-exploitation-cisco-catalyst-sd-wan-manager)
* **Primary Vulnerability Analyzed:** CVE-2026-20245 (Command Injection via CSV Tenant Upload)

---

## 📝 Executive Summary & Attack Description
In this attack, a highly sophisticated threat actor targeted a service provider’s Cisco Catalyst SD-WAN infrastructure. The attacker initially bypassed remote authentication mechanisms using secondary zero-day flaws to log in via SSH using the default `vmanage-admin` administrative account. Once inside, they executed a password reset to maintain exclusive access and lock out defenders. 

To elevate privileges, the attacker exploited a critical zero-day vulnerability (**CVE-2026-20245**) within the CLI’s tenant-upload feature by uploading a weaponized CSV file (`evil_tenant.csv`). This triggered a command injection that granted full **root-level access** to the underlying system. To establish persistent access, the threat actor modified the system's user database (`/etc/passwd`) to insert a backdoor root account named `troot`. Finally, the attacker performed anti-forensic operations, running cleanup scripts to delete their tools, restore original configurations, and clear logs.

---

## 🗺️ Attack Schema (Visual Flow)

```
[1. INITIAL ACCESS] ──> Bypassed edge plane authentication (CVE-2026-20127)
       │
[2. VALID ACCOUNTS] ──> Logged in via SSH using default 'vmanage-admin'
       │
[3. ACCOUNT MANIPULATION] ──> Changed administrator password to lock out defenders
       │
[4. PRIVILEGE ESCALATION] ──> Uploaded 'evil_tenant.csv' (Exploited CVE-2026-20245) ──> Gained Root
       │
[5. PERSISTENCE]    ──> Modified /etc/passwd directly to create 'troot' account
       │
[6. DEFENSE EVASION]──> Ran anti-forensic cleanup scripts & deleted 'evil_tenant.csv'
```

---

## 📊 Behaviors, Tactics, and Techniques Mapping

The table below maps the specific technical actions documented in the CTI report to the official MITRE ATT&CK enterprise matrix framework.

| Observed Behavior (From Report) | MITRE Tactic | Technique / Sub-technique | MITRE ID |
| :--- | :--- | :--- | :--- |
| Threat actor used previous zero-days (e.g., CVE-2026-20127) to bypass edge plane authentication mechanisms. | **Initial Access** | Exploit Public-Facing Application | **T1190** |
| Logged into the SD-WAN Manager using the factory-default `vmanage-admin` account via SSH interface. | **Initial Access** / **Persistence** | Valid Accounts | **T1078** |
| Changed the default administrator password immediately to lock out network defenders. | **Persistence** / **Defense Evasion** | Account Manipulation | **T1098** |
| Uploaded `evil_tenant.csv` to exploit the CVE-2026-20245 input-validation flaw to escape CLI restrictions. | **Privilege Escalation** | Exploitation for Privilege Escalation | **T1068** |
| Directly manipulated `/etc/passwd` to create a permanent hidden root account named `troot`. | **Persistence** | Create Account: Local Account | **T1136.001** |
| Gathered configuration state files from the SD-WAN fabric to blueprint the underlying system network. | **Discovery** | Network Information Discovery | **T1046** |
| Executed custom cleanup scripts to remove `evil_tenant.csv` and restore original database attributes. | **Defense Evasion** | Indicator Removal: File Deletion | **T1070.004** |