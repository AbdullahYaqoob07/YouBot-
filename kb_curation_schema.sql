-- Knowledge Base Curation Schema
-- Stores unanswered questions and admin responses for KB improvement

-- Table to store questions not found in KB
CREATE TABLE IF NOT EXISTS kb_unanswered_questions (
  id INT AUTO_INCREMENT PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  
  -- Question details
  user_question TEXT NOT NULL,
  user_language VARCHAR(50),
  
  -- AI's attempt
  ai_response TEXT,
  handoff_reason TEXT,
  unsolved_score FLOAT,
  
  -- Admin response
  admin_id VARCHAR(255),
  admin_response TEXT,
  admin_responded_at DATETIME,
  
  -- KB curation status
  status VARCHAR(50) DEFAULT 'pending', -- pending, reviewed, approved, rejected, added_to_kb
  reviewed_by_admin VARCHAR(255),
  reviewed_at DATETIME,
  
  -- KB ingestion
  added_to_kb TINYINT(1) DEFAULT 0,
  kb_document_id VARCHAR(255), -- Reference to vector store document
  added_to_kb_at DATETIME,
  added_by_admin VARCHAR(255),
  
  -- Metadata
  category VARCHAR(100), -- Admin can categorize (visa, housing, jobs, etc.)
  tags TEXT, -- JSON array of tags
  priority VARCHAR(50) DEFAULT 'normal', -- low, normal, high, critical
  notes TEXT, -- Admin notes
  
  -- Timestamps
  created_at DATETIME NOT NULL,
  updated_at DATETIME,
  
  -- Indexes for efficient queries
  INDEX idx_status (status),
  INDEX idx_user_id (user_id),
  INDEX idx_session (session_id),
  INDEX idx_added_to_kb (added_to_kb),
  INDEX idx_created (created_at),
  INDEX idx_priority (priority)
);

-- Table to track KB updates/additions
CREATE TABLE IF NOT EXISTS kb_update_history (
  id INT AUTO_INCREMENT PRIMARY KEY,
  
  -- Source of update
  source_type VARCHAR(50) NOT NULL, -- 'manual', 'admin_qa', 'bulk_upload', 'api'
  source_reference_id INT, -- References kb_unanswered_questions.id if from admin Q&A
  
  -- Content added
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  language VARCHAR(50),
  category VARCHAR(100),
  tags TEXT, -- JSON array
  
  -- Vector store details
  vector_store_type VARCHAR(50), -- pinecone, chroma, qdrant
  document_id VARCHAR(255), -- Vector store document ID
  namespace VARCHAR(255), -- For Pinecone
  
  -- Metadata
  added_by_admin VARCHAR(255) NOT NULL,
  added_at DATETIME NOT NULL,
  
  -- Quality metrics
  embedding_model VARCHAR(100),
  chunk_size INT,
  
  -- Indexes
  INDEX idx_source_type (source_type),
  INDEX idx_added_by (added_by_admin),
  INDEX idx_added_at (added_at),
  INDEX idx_category (category)
);

-- View for admin dashboard: pending KB curation items
CREATE OR REPLACE VIEW vw_kb_curation_pending AS
SELECT 
  uq.id,
  uq.session_id,
  uq.user_id,
  uq.user_question,
  uq.user_language,
  uq.admin_response,
  uq.admin_id,
  uq.admin_responded_at,
  uq.status,
  uq.category,
  uq.priority,
  uq.created_at,
  aa.admin_name,
  aa.admin_email,
  TIMESTAMPDIFF(HOUR, uq.created_at, NOW()) as hours_since_created
FROM kb_unanswered_questions uq
LEFT JOIN admin_availability aa ON uq.admin_id = aa.admin_id
WHERE uq.status IN ('pending', 'reviewed')
  AND uq.admin_response IS NOT NULL
  AND uq.added_to_kb = 0
ORDER BY 
  FIELD(uq.priority, 'critical', 'high', 'normal', 'low'),
  uq.created_at ASC;

-- View for KB update statistics
CREATE OR REPLACE VIEW vw_kb_update_stats AS
SELECT 
  DATE(added_at) as date,
  COUNT(*) as total_additions,
  COUNT(DISTINCT added_by_admin) as unique_admins,
  COUNT(DISTINCT category) as unique_categories,
  source_type,
  vector_store_type
FROM kb_update_history
GROUP BY DATE(added_at), source_type, vector_store_type
ORDER BY date DESC;

-- View for unanswered questions analytics
CREATE OR REPLACE VIEW vw_unanswered_questions_analytics AS
SELECT 
  DATE(created_at) as date,
  COUNT(*) as total_unanswered,
  COUNT(CASE WHEN status = 'approved' THEN 1 END) as approved_count,
  COUNT(CASE WHEN added_to_kb = 1 THEN 1 END) as added_to_kb_count,
  COUNT(DISTINCT category) as unique_categories,
  AVG(unsolved_score) as avg_unsolved_score,
  user_language as language
FROM kb_unanswered_questions
GROUP BY DATE(created_at), user_language
ORDER BY date DESC;

-- Stored procedure to approve and queue for KB addition
DELIMITER //
CREATE PROCEDURE sp_approve_for_kb(
  IN p_question_id INT,
  IN p_admin_id VARCHAR(255),
  IN p_category VARCHAR(100),
  IN p_tags TEXT,
  IN p_notes TEXT
)
BEGIN
  DECLARE v_status VARCHAR(50);
  
  -- Check if question exists and hasn't been added yet
  SELECT status INTO v_status
  FROM kb_unanswered_questions
  WHERE id = p_question_id;
  
  IF v_status IS NULL THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Question not found';
  END IF;
  
  IF v_status = 'added_to_kb' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Question already added to KB';
  END IF;
  
  -- Update question record
  UPDATE kb_unanswered_questions
  SET status = 'approved',
      reviewed_by_admin = p_admin_id,
      reviewed_at = NOW(),
      category = p_category,
      tags = p_tags,
      notes = p_notes,
      updated_at = NOW()
  WHERE id = p_question_id;
  
  SELECT 'approved' as result;
END//
DELIMITER ;

-- Stored procedure to mark as added to KB
DELIMITER //
CREATE PROCEDURE sp_mark_added_to_kb(
  IN p_question_id INT,
  IN p_document_id VARCHAR(255),
  IN p_admin_id VARCHAR(255)
)
BEGIN
  UPDATE kb_unanswered_questions
  SET added_to_kb = 1,
      kb_document_id = p_document_id,
      added_to_kb_at = NOW(),
      added_by_admin = p_admin_id,
      status = 'added_to_kb',
      updated_at = NOW()
  WHERE id = p_question_id;
  
  SELECT 'added' as result;
END//
DELIMITER ;
