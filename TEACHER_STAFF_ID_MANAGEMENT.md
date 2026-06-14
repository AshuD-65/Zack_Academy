# Teacher & Staff ID Management Guide

## 📋 Overview

This guide explains how to manage teachers and Staff IDs when teachers leave the academy.

---

## 🎯 Understanding the System

### **Staff ID Lifecycle:**

```
1. Admin creates Staff ID → Invitation sent to teacher email
2. Teacher registers using Staff ID → Staff ID marked as "used"
3. Teacher works at academy → Active account
4. Teacher leaves academy → Admin deletes teacher
5. Staff ID is released → Can be deleted or reused
```

---

## 🚀 **NEW FEATURE: Auto-Release Staff IDs**

### **What Changed:**

When you delete a teacher, the system now:
- ✅ Deletes the teacher account
- ✅ **Automatically releases their Staff ID**
- ✅ Staff ID becomes available for deletion
- ✅ You get a confirmation message

**Example message:**
```
✅ Teacher "John Doe" deleted. Staff ID STF003 is now available for reuse.
```

---

## 📖 **How to Delete Teacher When They Leave**

### **Step-by-Step Process:**

#### **Step 1: Go to Teachers Page**
1. Log in to Admin Dashboard
2. Click **"Teachers"** in the sidebar
3. You'll see all teachers with their Staff IDs displayed

#### **Step 2: Delete the Teacher**
1. Find the teacher who is leaving
2. Click the **"Delete"** button
3. Confirm the deletion
4. ✅ Teacher deleted & Staff ID released!

#### **Step 3: (Optional) Delete the Staff ID**
1. Go to **"Staff IDs"** page
2. Find the released Staff ID
3. Click **"Delete"** button
4. Confirm deletion

---

## 🔄 **What Happens to Teacher's Data?**

When you delete a teacher:

| Item | What Happens |
|------|-------------|
| **Teacher Account** | ❌ Deleted permanently |
| **Staff ID Invitation** | ✅ Released (can be deleted) |
| **Teacher's Courses** | ⚠️ Remain but teacher field = null |
| **Course Materials** | ✅ Remain unchanged |
| **Student Enrollments** | ✅ Remain unchanged |
| **Assignments/Submissions** | ✅ Remain unchanged |

---

## 💡 **Options for Handling Departing Teachers**

### **Option 1: Delete Teacher (Clean Removal)** ⭐

**When to use**: Teacher permanently left, courses will be reassigned

**Steps:**
```
1. Admin Dashboard → Teachers
2. Click "Delete" on teacher
3. Staff ID is released automatically
4. Optionally delete Staff ID from Staff IDs page
```

**Result:**
- Teacher account gone
- Staff ID available for reuse/deletion
- Courses remain but need reassignment

---

### **Option 2: Keep Teacher, Reassign Courses**

**When to use**: Teacher left but you want to keep historical data

**Steps:**
```
1. Admin Dashboard → Courses
2. Edit each course by the departed teacher
3. Assign to a new teacher
4. Don't delete the teacher account
```

**Result:**
- Teacher account remains (for records)
- Courses assigned to new teacher
- All historical data preserved

---

### **Option 3: Delete Teacher, Keep Staff ID**

**When to use**: Teacher left but you want invitation records

**Steps:**
```
1. Delete the teacher (as in Option 1)
2. DON'T delete the Staff ID invitation
```

**Result:**
- Teacher account gone
- Staff ID invitation remains for audit trail
- Staff ID marked as "unused" again

---

## 🆕 **Staff ID Features**

### **What You Can See:**

**On Teachers Page:**
- Teacher ID
- Name & Profile Picture
- Email
- **Staff ID** (displayed as badge)
- Actions (Edit/Delete)

**On Staff IDs Page:**
- Staff ID number
- Email sent to
- Created date
- Sent date
- **Used status** (Yes/No)
- Delete action (if unused)

---

## 📊 **Staff ID Status Meanings**

| Status | Meaning | Can Delete? |
|--------|---------|-------------|
| **Used: Yes** | Teacher registered with this ID | ❌ No (teacher exists) |
| **Used: No** | Invitation sent but not used yet | ✅ Yes |
| **Released** | Teacher was deleted, ID freed | ✅ Yes |

---

## ⚙️ **Admin Workflows**

### **Workflow 1: Teacher Leaves Academy**

```
1. Admin Dashboard → Teachers
2. Find teacher → Click "Delete"
3. Confirm deletion
4. Message: "Teacher deleted. Staff ID STF003 now available"
5. (Optional) Go to Staff IDs → Delete STF003
```

**Time**: 30 seconds

---

### **Workflow 2: Reuse Released Staff ID**

```
1. Teacher leaves (deleted as above)
2. Staff ID is released (shows as "Used: No")
3. Admin can keep the Staff ID for new teacher
4. Or delete it to clean up records
```

---

### **Workflow 3: Accidental Deletion Recovery**

⚠️ **Important**: Teacher deletion is permanent!

**If deleted by mistake:**
- Cannot recover the account
- Need to create new teacher account
- Can reuse the same Staff ID
- Or create new Staff ID

**Prevention**:
- Confirmation dialog prevents accidents
- Always verify before clicking "Delete"

---

## 🔐 **Security & Data Integrity**

### **What's Protected:**

✅ **Student Data**: Never affected by teacher deletion  
✅ **Course Content**: Materials remain accessible  
✅ **Enrollments**: Students stay enrolled  
✅ **Submissions**: Assignment submissions preserved  
✅ **Grades**: All grades remain in system  

### **What's Removed:**

❌ **Teacher Login**: Cannot access system anymore  
❌ **Teacher Dashboard**: No longer available  
❌ **Profile Info**: Name, email, picture removed  

---

## 📝 **Best Practices**

### ✅ **Do:**
- Review teacher's courses before deletion
- Reassign courses to active teachers
- Keep Staff ID invitations for audit trail
- Document reason for teacher departure

### ❌ **Don't:**
- Delete teachers without checking their courses
- Reuse Staff IDs immediately (wait 30 days)
- Delete Staff ID invitations unless necessary
- Share Staff IDs with multiple teachers

---

## 🔍 **Audit Trail**

The system maintains records:

| Event | Recorded Information |
|-------|---------------------|
| **Staff ID Created** | Date, email, staff ID number |
| **Invitation Sent** | Sent date, recipient |
| **Teacher Registered** | Used date (when they signed up) |
| **Teacher Deleted** | Message shown, Staff ID released |

**View history**: Admin Dashboard → Staff IDs

---

## ❓ **FAQs**

### **Q: Can I reuse a Staff ID after deleting a teacher?**
A: Yes! The new system releases Staff IDs automatically when teachers are deleted.

### **Q: What happens to courses when teacher is deleted?**
A: Courses remain but the teacher field becomes null. Reassign them to another teacher.

### **Q: Can I undo teacher deletion?**
A: No, deletion is permanent. You'll need to create a new account.

### **Q: Should I delete or keep Staff ID invitations?**
A: Keep them for audit trail unless you need to clean up old records.

### **Q: How do I see which Staff IDs are available?**
A: Go to Staff IDs page. "Used: No" means available.

### **Q: Can multiple teachers share a Staff ID?**
A: No, each Staff ID is unique to one teacher.

---

## 🛠️ **Troubleshooting**

### **Issue: Can't delete Staff ID**

**Problem**: "Staff ID has already been used and cannot be deleted"

**Solution**:
1. Check if teacher still exists
2. If yes, delete teacher first
3. Then delete Staff ID
4. If issue persists, check database

---

### **Issue: Deleted teacher but Staff ID still shows "Used: Yes"**

**Problem**: Old system didn't release Staff IDs

**Solution**:
1. This was fixed in the latest update
2. Future deletions will work correctly
3. For old Staff IDs, admin needs database access

---

### **Issue: Teacher's courses missing after deletion**

**Solution**:
- Courses are NOT deleted when teacher is deleted
- Go to Courses page
- Look for courses with no teacher assigned
- Reassign them to active teachers

---

## 📞 **Need Help?**

If you encounter issues:
1. Check this documentation first
2. Review the FAQs section
3. Check Render deployment logs
4. Contact system administrator

---

## 🎯 **Quick Reference**

**Delete Teacher:**
```
Dashboard → Teachers → Delete → Confirm
```

**Delete Released Staff ID:**
```
Dashboard → Staff IDs → Delete → Confirm
```

**Reassign Courses:**
```
Dashboard → Courses → Edit Course → Select New Teacher
```

---

**Last Updated**: June 14, 2026  
**Feature**: Auto-Release Staff IDs on Teacher Deletion  
**Status**: Active ✅
