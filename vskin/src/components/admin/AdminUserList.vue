<template>
  <div class="users-section animate-fade-in">
    <div class="page-header">
      <div class="page-header-content">
        <div class="page-header-icon"><UserFilled /></div>
        <div class="page-header-text">
          <h2>用户管理</h2>
          <p class="subtitle">管理站内所有用户及其角色的状态与权限</p>
        </div>
      </div>
      <div class="page-header-actions">
        <el-button type="primary" :icon="Refresh" @click="refreshUsers" plain class="hover-lift">
          刷新列表
        </el-button>
      </div>
    </div>

    <el-card class="surface-card" shadow="never">
      <el-table :data="users" style="width: 100%" class="modern-table" v-loading="loading">
        <el-table-column prop="display_name" label="用户名" min-width="150">
          <template #default="{ row }">
            <div class="user-cell">
              <el-avatar :size="32" :src="row.avatar_url" shape="square" class="mr-2 user-avatar">
                {{ row.display_name?.charAt(0).toUpperCase() || row.email.charAt(0).toUpperCase() }}
              </el-avatar>
              <span>{{ row.display_name || '未设置' }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="email" label="邮箱" min-width="220" />
        <el-table-column label="身份状态" width="120">
          <template #default="{ row }">
            <el-tag
              :type="getUserGroupInfo(row).tagType"
              effect="light"
              size="small"
            >{{ getUserGroupInfo(row).title }}</el-tag>
            <el-tag v-if="getUserBanStatus(row)" type="warning" effect="light" size="small" class="ml-2">已封禁</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="角色数" width="100" align="center">
          <template #default="{ row }">
            <el-badge :value="row.profile_count || 0" :type="row.profile_count > 0 ? 'primary' : 'info'" class="profile-badge" />
          </template>
        </el-table-column>
        <el-table-column label="管理操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button
              size="small"
              type="primary"
              @click="showUserDetailDialog(row)"
              plain
              class="hover-lift"
            >
              管理
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- User Detail Dialog -->
    <el-dialog
      v-model="userDetailDialogVisible"
      title="用户详情"
      width="800px"
      append-to-body
      align-center
      destroy-on-close
    >
      <div v-if="currentUser" class="user-detail-container">
        <!-- User Identity Panel -->
        <div class="identity-panel mb-6">
          <el-avatar :size="80" :src="currentUser.avatar_url" shape="square" class="panel-avatar">
            {{ currentUser.email.charAt(0).toUpperCase() }}
          </el-avatar>
          <div class="panel-info">
            <div class="panel-name">
              <h3>{{ currentUser.display_name || '未设置显示名' }}</h3>
              <el-tag :type="getUserGroupInfo(currentUser).tagType" size="small" class="ml-2">
                {{ getUserGroupInfo(currentUser).title }}
              </el-tag>
            </div>
            <div class="panel-email">{{ currentUser.email }}</div>
            <div class="panel-id">UID: {{ currentUser.id }}</div>
          </div>
          <div class="panel-status">
            <div v-if="getUserBanStatus(currentUser)" class="ban-info">
              <el-tag type="warning" effect="dark">
                <el-icon><Warning /></el-icon> 封禁中
              </el-tag>
              <div class="ban-timer">{{ formatBanRemaining(currentUser.banned_until) }} 后解封</div>
            </div>
            <el-tag v-else type="success" effect="dark">
              <el-icon><CircleCheck /></el-icon> 状态正常
            </el-tag>
          </div>
        </div>

        <el-tabs type="border-card" class="detail-tabs">
          <el-tab-pane label="角色列表">
            <el-table :data="currentUser.profiles || []" size="small" max-height="300">
              <el-table-column prop="name" label="角色名称" />
              <el-table-column prop="model" label="模型" width="100">
                <template #default="{ row }">
                  <el-tag size="small" :type="row.model === 'slim' ? 'success' : 'info'">{{ row.model }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="id" label="角色 UUID" width="300" />
            </el-table>
            <el-empty v-if="!currentUser.profiles?.length" description="该用户暂无角色" :image-size="60" />
          </el-tab-pane>
          
          <el-tab-pane label="危险操作">
            <div class="actions-grid">
              <div class="action-card-item">
                <div class="action-text-box">
                  <div class="a-title">用户组</div>
                  <div class="a-desc">可设置为用户、老师，超级管理员可额外设置为管理员。</div>
                </div>
                <div class="group-editor">
                  <el-select v-model="pendingUserGroup" size="small" style="width: 140px">
                    <el-option
                      v-for="item in userGroupOptions"
                      :key="item.value"
                      :label="item.label"
                      :value="item.value"
                      :disabled="!canAssignGroup(item.value)"
                    />
                  </el-select>
                  <el-button
                    type="primary"
                    size="small"
                    @click="setUserGroup(currentUser)"
                    :disabled="isCurrentUserSelf(currentUser) || pendingUserGroup === getUserGroupKey(currentUser)"
                    class="hover-lift"
                  >保存</el-button>
                </div>
              </div>

              <div class="action-card-item">
                <div class="action-text-box">
                  <div class="a-title">账号封禁</div>
                  <div class="a-desc">暂时禁止该用户登录 Minecraft 客户端。</div>
                </div>
                <el-button 
                  v-if="!getUserBanStatus(currentUser)" 
                  type="warning" 
                  @click="showBanDialog"
                  :disabled="getUserGroupKey(currentUser) === 'super_admin' || isCurrentUserSelf(currentUser)"
                  class="hover-lift"
                >
                  执行封禁
                </el-button>
                <el-button v-else type="success" @click="unbanUser(currentUser)" class="hover-lift">
                  解除封禁
                </el-button>
              </div>

              <div class="action-card-item">
                <div class="action-text-box">
                  <div class="a-title">强制重置密码</div>
                  <div class="a-desc">系统管理员手动为该用户设置新密码。</div>
                </div>
                <el-button @click="showResetPasswordDialog(currentUser)" class="hover-lift">
                  重置密码
                </el-button>
              </div>

              <div class="action-card-item dangerous">
                <div class="action-text-box">
                  <div class="a-title">注销账号</div>
                  <div class="a-desc">永久删除该用户及其所有关联的角色、皮肤。</div>
                </div>
                <el-button 
                  type="danger" 
                  @click="deleteUser(currentUser)"
                  :disabled="getUserGroupKey(currentUser) === 'super_admin' || isCurrentUserSelf(currentUser)"
                  class="hover-lift"
                >
                  删除用户
                </el-button>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-dialog>

    <!-- Reset Password Dialog -->
    <el-dialog v-model="resetPasswordDialogVisible" title="重置用户密码" width="400px" append-to-body align-center>
      <el-form label-position="top">
        <el-form-item label="新密码 (最少6位)">
          <el-input v-model="resetPasswordForm.new_password" type="password" show-password />
        </el-form-item>
        <el-form-item label="确认新密码">
          <el-input v-model="resetPasswordForm.confirm_password" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPasswordDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmResetPassword" :loading="resetting">确认重置</el-button>
      </template>
    </el-dialog>

    <!-- Ban User Dialog -->
    <el-dialog v-model="banDialogVisible" title="设置封禁时长" width="450px" append-to-body align-center>
      <div class="ban-dialog-body">
        <el-radio-group v-model="banDurationType" class="mb-4 capsule-radio">
          <el-radio-button value="preset">快速选择</el-radio-button>
          <el-radio-button value="custom">精确小时</el-radio-button>
        </el-radio-group>

        <div v-if="banDurationType === 'preset'" class="preset-durations mb-4">
          <el-button 
            v-for="p in presetDurations" 
            :key="p.value" 
            :type="banPresetDuration === p.value ? 'primary' : ''"
            size="small"
            @click="banPresetDuration = p.value"
          >{{ p.label }}</el-button>
        </div>
        
        <div v-else class="custom-duration mb-4">
          <el-input-number v-model="banCustomHours" :min="1" :max="8760" style="width: 100%" />
        </div>

        <div class="ban-preview">
          解封时间：<span>{{ formatBanUntilTime() }}</span>
        </div>
      </div>
      <template #footer>
        <el-button @click="banDialogVisible = false">取消</el-button>
        <el-button type="danger" @click="confirmBanUser" :loading="banning">确认封禁</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import axios from 'axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  Refresh, UserFilled, Warning, CircleCheck 
} from '@element-plus/icons-vue'

const users = ref([])
const loading = ref(false)
const currentUser = ref(null)
const userDetailDialogVisible = ref(false)
const resetPasswordDialogVisible = ref(false)
const resetPasswordForm = ref({ new_password: '', confirm_password: '' })
const resetting = ref(false)
const banDialogVisible = ref(false)
const banDurationType = ref('preset')
const banPresetDuration = ref(24)
const banCustomHours = ref(24)
const banning = ref(false)
const pendingUserGroup = ref('user')
const actorGroup = ref('user')

const userGroupOptions = [
  { label: '用户', value: 'user' },
  { label: '老师', value: 'teacher' },
  { label: '管理员', value: 'admin' },
]

const presetDurations = [
  { label: '1小时', value: 1 }, { label: '1天', value: 24 }, 
  { label: '3天', value: 72 }, { label: '7天', value: 168 }, { label: '30天', value: 720 }
]

const authHeaders = () => ({ Authorization: 'Bearer ' + localStorage.getItem('jwt') })

async function refreshUsers() {
  loading.value = true
  try {
    const [usersRes, meRes] = await Promise.all([
      axios.get('/admin/users', { headers: authHeaders() }),
      axios.get('/me', { headers: authHeaders() }),
    ])
    users.value = usersRes.data
    actorGroup.value = meRes.data?.user_group || (meRes.data?.is_admin ? 'admin' : 'user')
  } catch (e) {
    ElMessage.error('加载用户列表失败')
  } finally {
    loading.value = false
  }
}

async function showUserDetailDialog(user) {
  try {
    const res = await axios.get(`/admin/users/${user.id}`, { headers: authHeaders() })
    currentUser.value = res.data
    pendingUserGroup.value = getUserGroupKey(res.data)
    userDetailDialogVisible.value = true
  } catch (e) {
    ElMessage.error('无法加载用户详情')
  }
}

function getUserGroupKey(user) {
  return user?.user_group || (user?.is_admin ? 'admin' : 'user')
}

function getUserGroupInfo(user) {
  const key = getUserGroupKey(user)
  const map = {
    super_admin: { title: '超级管理员', tagType: 'danger' },
    admin: { title: '管理员', tagType: 'primary' },
    user: { title: '用户', tagType: 'success' },
    teacher: { title: '老师', tagType: 'info' },
  }
  return map[key] || map.user
}

function canAssignGroup(group) {
  if (group === 'admin') return actorGroup.value === 'super_admin'
  return group !== 'super_admin'
}

async function setUserGroup(user) {
  try {
    await ElMessageBox.confirm(`确定将 ${user.email} 设置为 ${getUserGroupInfo({ user_group: pendingUserGroup.value }).title} 吗？`, '确认', { type: 'warning' })
    await axios.post(`/admin/users/${user.id}/set-group`, { user_group: pendingUserGroup.value }, { headers: authHeaders() })
    ElMessage.success('操作成功')
    await refreshUsers()
    if (currentUser.value) {
      currentUser.value.user_group = pendingUserGroup.value
      currentUser.value.is_admin = pendingUserGroup.value === 'super_admin' || pendingUserGroup.value === 'admin'
    }
  } catch (e) {}
}

async function deleteUser(user) {
  try {
    await ElMessageBox.confirm('永久删除该用户？此操作不可逆！', '极端警告', { type: 'error' })
    await axios.delete(`/admin/users/${user.id}`, { headers: authHeaders() })
    ElMessage.success('用户已删除')
    userDetailDialogVisible.value = false
    refreshUsers()
  } catch (e) {}
}

function showResetPasswordDialog(user) {
  resetPasswordForm.value = { new_password: '', confirm_password: '' }
  resetPasswordDialogVisible.value = true
}

async function confirmResetPassword() {
  const f = resetPasswordForm.value
  if (!f.new_password || f.new_password.length < 6) return ElMessage.error('密码长度不足')
  if (f.new_password !== f.confirm_password) return ElMessage.error('两次密码不一致')
  
  resetting.value = true
  try {
    await axios.post('/admin/users/reset-password', {
      user_id: currentUser.value.id,
      new_password: f.new_password
    }, { headers: authHeaders() })
    ElMessage.success('密码已重置')
    resetPasswordDialogVisible.value = false
  } catch (e) {
    ElMessage.error('重置失败')
  } finally {
    resetting.value = false
  }
}

function showBanDialog() {
  banDialogVisible.value = true
}

async function confirmBanUser() {
  const hours = banDurationType.value === 'preset' ? banPresetDuration.value : banCustomHours.value
  const bannedUntil = Date.now() + hours * 60 * 60 * 1000
  
  banning.value = true
  try {
    await axios.post(`/admin/users/${currentUser.value.id}/ban`, { banned_until: bannedUntil }, { headers: authHeaders() })
    ElMessage.success('封禁已执行')
    banDialogVisible.value = false
    refreshUsers()
    if (currentUser.value) currentUser.value.banned_until = bannedUntil
  } catch (e) {
    ElMessage.error('封禁失败')
  } finally {
    banning.value = false
  }
}

async function unbanUser(user) {
  try {
    await axios.post(`/admin/users/${user.id}/unban`, {}, { headers: authHeaders() })
    ElMessage.success('封禁已解除')
    refreshUsers()
    if (currentUser.value) currentUser.value.banned_until = 0
  } catch (e) {}
}

// Helpers
const getUserBanStatus = (user) => user.banned_until && Date.now() < user.banned_until
const isCurrentUserSelf = (user) => {
  try {
    const token = localStorage.getItem('jwt')
    if (!token) return false
    return JSON.parse(atob(token.split('.')[1])).sub === user.id
  } catch (e) { return false }
}
const formatBanRemaining = (ts) => {
  const m = Math.ceil((ts - Date.now()) / 60000)
  if (m > 1440) return Math.floor(m / 1440) + ' 天'
  if (m > 60) return Math.floor(m / 60) + ' 小时'
  return m + ' 分钟'
}
const formatBanUntilTime = () => {
  const h = banDurationType.value === 'preset' ? banPresetDuration.value : banCustomHours.value
  return new Date(Date.now() + h * 3600000).toLocaleString()
}

onMounted(refreshUsers)
</script>

<style scoped>
@import "@/assets/styles/animations.css";
@import "@/assets/styles/layout.css";
@import "@/assets/styles/cards.css";
@import "@/assets/styles/tags.css";
@import "@/assets/styles/buttons.css";
@import "@/assets/styles/headers.css";

.users-section { max-width: 1000px; margin: 0 auto; padding: 20px 0; }

.user-cell { display: flex; align-items: center; }
.user-avatar { border-radius: 8px; flex-shrink: 0; }

/* Dialog Styles */
.user-detail-container { padding: 24px; }
.identity-panel { display: flex; align-items: center; gap: 24px; padding: 20px; background: var(--color-background-soft); border-radius: 12px; }
.panel-avatar { background: var(--color-background-soft); color: white; font-weight: bold; border-radius: 10px; border: 1px solid var(--color-border); box-shadow: none; }
.panel-info { flex: 1; }
.panel-name { display: flex; align-items: center; gap: 8px; }
.panel-name h3 { margin: 0; font-size: 20px; color: var(--color-heading); }
.panel-email { color: var(--color-text-light); margin-top: 4px; }
.panel-id { font-size: 11px; font-family: monospace; color: var(--color-text-light); margin-top: 4px; }
.panel-status { text-align: right; }
.ban-timer { font-size: 12px; color: var(--el-color-warning); margin-top: 4px; }

.actions-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 10px 0; }
.action-card-item { display: flex; justify-content: space-between; align-items: center; padding: 16px; background: var(--color-background-soft); border-radius: 10px; border: 1px solid var(--color-border); }
.action-card-item.dangerous { border-color: rgba(245, 108, 108, 0.3); }
.action-text-box { flex: 1; margin-right: 12px; }
.a-title { font-weight: 600; font-size: 14px; color: var(--color-heading); }
.a-desc { font-size: 12px; color: var(--color-text-light); margin-top: 2px; }
.group-editor { display: flex; gap: 8px; align-items: center; }

.ban-preview { font-size: 13px; color: var(--color-text-light); padding: 10px; background: var(--color-background-mute); border-radius: 6px; }
.ban-preview span { font-weight: bold; color: var(--el-color-primary); }

.mr-2 { margin-right: 8px; }
.mb-4 { margin-bottom: 16px; }
.mb-6 { margin-bottom: 24px; }

@media (max-width: 768px) {
  .actions-grid { grid-template-columns: 1fr; }
}
</style>
