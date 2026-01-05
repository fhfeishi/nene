// web/zzJS/server.js

const express = require('express');
const http = require('http');
const socketIo = require('socket.io');
const cors = require('cors');
const path = require('path');
const axios = require('axios');
const multer = require('multer');
const fs = require('fs');

const app = express();
const server = http.createServer(app);
const io = socketIo(server, {
  cors: {
    origin: "*",
    methods: ["GET", "POST"]
  }
});

// 中间件
app.use(cors());
app.use(express.json());
app.use(express.static(path.join(__dirname, 'src')));

// 文件上传配置
const upload = multer({
  dest: 'uploads/',
  limits: {
    fileSize: 10 * 1024 * 1024 // 10MB
  }
});

// Python后端配置
const PYTHON_BACKEND_URL = 'http://localhost:8000';

// 存储用户会话
const userSessions = new Map();

// WebSocket连接处理
io.on('connection', (socket) => {
  console.log('用户连接:', socket.id);
  
  // 初始化用户会话
  userSessions.set(socket.id, {
    chatHistory: [],
    isTyping: false
  });

  // 处理文本消息
  socket.on('send_message', async (data) => {
    try {
      const { message, sessionId } = data;
      const userSession = userSessions.get(socket.id);
      
      if (!userSession) {
        socket.emit('error', { message: '会话不存在' });
        return;
      }

      // 添加用户消息到历史记录
      userSession.chatHistory.push({
        role: 'user',
        content: message,
        timestamp: new Date().toISOString()
      });

      // 发送给Python后端进行流式处理
      await streamResponseToClient(socket, message, userSession.chatHistory);
      
    } catch (error) {
      console.error('处理消息错误:', error);
      socket.emit('error', { message: '处理消息时发生错误' });
    }
  });

  // 处理语音消息
  socket.on('send_audio', async (data) => {
    try {
      const { audioData, sessionId } = data;
      const userSession = userSessions.get(socket.id);
      
      if (!userSession) {
        socket.emit('error', { message: '会话不存在' });
        return;
      }

      // 发送音频到Python后端进行语音识别
      const response = await axios.post(`${PYTHON_BACKEND_URL}/api/voice/transcribe`, {
        audio_data: audioData
      }, {
        headers: {
          'Content-Type': 'application/json'
        }
      });

      const transcribedText = response.data.text;
      
      // 添加转录文本到历史记录
      userSession.chatHistory.push({
        role: 'user',
        content: transcribedText,
        timestamp: new Date().toISOString(),
        isVoice: true
      });

      // 发送给Python后端进行流式处理
      await streamResponseToClient(socket, transcribedText, userSession.chatHistory);
      
    } catch (error) {
      console.error('处理语音消息错误:', error);
      socket.emit('error', { message: '处理语音消息时发生错误' });
    }
  });

  // 处理打字状态
  socket.on('typing', (data) => {
    const userSession = userSessions.get(socket.id);
    if (userSession) {
      userSession.isTyping = data.isTyping;
      socket.broadcast.emit('user_typing', {
        userId: socket.id,
        isTyping: data.isTyping
      });
    }
  });

  // 处理断开连接
  socket.on('disconnect', () => {
    console.log('用户断开连接:', socket.id);
    userSessions.delete(socket.id);
  });
});

// 流式响应处理函数
async function streamResponseToClient(socket, message, chatHistory) {
  try {
    // 通知客户端开始接收响应
    socket.emit('response_start', { message: '开始生成回答...' });

    // 调用Python后端的流式API
    const response = await axios.post(`${PYTHON_BACKEND_URL}/api/chat/stream`, {
      question: message,
      chat_history: chatHistory.slice(-10) // 只发送最近10条历史记录
    }, {
      headers: {
        'Content-Type': 'application/json'
      },
      responseType: 'stream'
    });

    let fullResponse = '';
    let isFirstChunk = true;

    response.data.on('data', (chunk) => {
      try {
        const lines = chunk.toString().split('\n');
        
        for (const line of lines) {
          if (line.trim() === '') continue;
          
          if (line.startsWith('data: ')) {
            const data = line.slice(6);
            
            if (data === '[DONE]') {
              // 响应完成
              socket.emit('response_end', { 
                fullResponse,
                timestamp: new Date().toISOString()
              });
              
              // 更新用户会话历史
              const userSession = userSessions.get(socket.id);
              if (userSession) {
                userSession.chatHistory.push({
                  role: 'assistant',
                  content: fullResponse,
                  timestamp: new Date().toISOString()
                });
              }
              return;
            }
            
            try {
              const parsed = JSON.parse(data);
              if (parsed.content) {
                if (isFirstChunk) {
                  socket.emit('response_chunk', { 
                    content: parsed.content,
                    isFirst: true
                  });
                  isFirstChunk = false;
                } else {
                  socket.emit('response_chunk', { 
                    content: parsed.content,
                    isFirst: false
                  });
                }
                fullResponse += parsed.content;
              }
            } catch (parseError) {
              console.error('解析流式数据错误:', parseError);
            }
          }
        }
      } catch (error) {
        console.error('处理流式数据错误:', error);
      }
    });

    response.data.on('end', () => {
      console.log('流式响应结束');
    });

    response.data.on('error', (error) => {
      console.error('流式响应错误:', error);
      socket.emit('error', { message: '响应生成过程中发生错误' });
    });

  } catch (error) {
    console.error('调用Python后端错误:', error);
    socket.emit('error', { message: '无法连接到AI服务' });
  }
}

// REST API路由
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'src', 'index.html'));
});

// 健康检查
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok', 
    timestamp: new Date().toISOString(),
    connections: userSessions.size
  });
});

// 获取聊天历史
app.get('/api/chat/history/:sessionId', (req, res) => {
  const { sessionId } = req.params;
  // 这里可以实现从数据库获取历史记录的逻辑
  res.json({ history: [] });
});

// 文件上传处理
app.post('/api/upload', upload.single('file'), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: '没有文件上传' });
  }
  
  res.json({
    message: '文件上传成功',
    filename: req.file.filename,
    originalname: req.file.originalname
  });
});

// 错误处理中间件
app.use((error, req, res, next) => {
  console.error('服务器错误:', error);
  res.status(500).json({ error: '内部服务器错误' });
});

// 启动服务器
const PORT = process.env.PORT || 3000;
server.listen(PORT, () => {
  console.log(`🚀 前端服务器运行在 http://localhost:${PORT}`);
  console.log(`📡 WebSocket服务器已启动`);
  console.log(`🔗 Python后端地址: ${PYTHON_BACKEND_URL}`);
});

// 优雅关闭
process.on('SIGTERM', () => {
  console.log('收到SIGTERM信号，正在关闭服务器...');
  server.close(() => {
    console.log('服务器已关闭');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('收到SIGINT信号，正在关闭服务器...');
  server.close(() => {
    console.log('服务器已关闭');
    process.exit(0);
  });
});
