pipeline {
    agent any

    options {
        timeout(time: 30, unit: 'MINUTES')
        disableConcurrentBuilds()
        // 可选：自动丢弃旧构建，只保留最近 30 次，防止 keepAll=true 撑爆磁盘
        buildDiscarder(logRotator(numToKeepStr: '30'))
    }

    parameters {
        choice(name: 'ENV', choices: ['dev', 'prod'], description: '选择运行环境')
        choice(name: 'MARK', choices: ['all', 'smoke', 'regression'], description: '选择用例标记')
    }

    environment {
        // ========== 系统路径 ==========
        PYTHON_PATH = 'C:/Users/27088/AppData/Local/Programs/Python/Python310/python.exe'

        // ========== 【新增】pip 依赖源（已提取为环境变量）==========
        PIP_INDEX_URL = 'https://pypi.tuna.tsinghua.edu.cn/simple'

        // ========== Allure 报告相关 ==========
        ALLURE_RESULTS = 'reports/allure-results'
        ALLURE_REPORT_DIR = 'reports/allure-report'
        ALLURE_REPORT_NAME = 'AllureReport'

        // ========== 邮件配置 ==========
        MAIL_RECIPIENT = 'yiming_2333@sina.com'

        // ========== 编码设置 ==========
        PYTHONIOENCODING = 'utf-8'

        // ========== Git 配置 ==========
        GIT_URL = 'https://github.com/yiming2333/api_test.git'
        GIT_BRANCH = 'master'
        GIT_CREDENTIALS_ID = ''

        // ========== 报告链接（严格按你的格式，不改动）==========
        REPORT_LINK = "${env.JENKINS_URL}job/${env.JOB_NAME}/${env.BUILD_NUMBER}/${env.ALLURE_REPORT_NAME}/"
    }

    stages {
        // ========== 【新增】获取触发人（需先安装 Build User Vars Plugin）==========
        stage('0. 获取构建用户') {
            steps {
                script {
                    try {
                        wrap([$class: 'BuildUser']) {
                            // 把触发人存到全局环境变量，供 post 使用
                            env.TRIGGER_USER = env.BUILD_USER_ID ?: '未知(插件未生效)'
                        }
                    } catch (e) {
                        echo "⚠️ 无法获取构建用户(请确认已安装 Build User Vars Plugin): ${e.message}"
                        env.TRIGGER_USER = '未知'
                    }
                    echo "本次构建触发人: ${env.TRIGGER_USER}"
                }
            }
        }

        stage('1. 拉取代码') {
            options { retry(3) }
            steps {
                echo "正在从 Git 拉取代码..."
                script {
                    def gitConfig = [branch: env.GIT_BRANCH, url: env.GIT_URL]
                    if (env.GIT_CREDENTIALS_ID?.trim()) {
                        gitConfig.credentialsId = env.GIT_CREDENTIALS_ID
                    }
                    git gitConfig
                }
            }
        }

        stage('2. 安装依赖') {
            steps {
                echo "正在安装 Python 依赖..."
                bat """
                    chcp 65001
                    "${PYTHON_PATH}" -m pip install -r requirements.txt -q -i ${PIP_INDEX_URL}
                """
            }
        }

        stage('3. 执行测试') {
            steps {
                echo "开始执行 Pytest 测试..."
                script {
                    catchError(buildResult: 'FAILURE', stageResult: 'FAILURE') {
                        def markArg = params.MARK != 'all' ? "-m ${params.MARK}" : ""
                        bat """
                            chcp 65001
                            "${PYTHON_PATH}" -m pytest ${markArg} ^
                                --env=${params.ENV} ^
                                --alluredir=${ALLURE_RESULTS} ^
                                --clean-alluredir ^
                                -v
                        """
                    }
                }
            }
        }

        stage('4. 生成并发布 Allure 报告') {
            steps {
                echo "正在生成 Allure 测试报告..."
                script {
                    try {
                        bat """
                            chcp 65001
                            allure generate ${ALLURE_RESULTS} -o ${ALLURE_REPORT_DIR} --clean
                        """
                    } catch (e) {
                        echo "⚠️ Allure 报告生成异常: ${e.message}"
                    }
                }

                publishHTML([
                    reportDir: env.ALLURE_REPORT_DIR,
                    reportFiles: 'index.html',
                    reportName: env.ALLURE_REPORT_NAME,
                    allowMissing: true,
                    keepAll: true,              // 🔴 改为 true！保留所有历史构建报告
                    alwaysLinkToLastBuild: false
                ])
            }
        }
    }

    post {
        always {
            echo "流水线执行结束"
            archiveArtifacts artifacts: 'logs/*.log', allowEmptyArchive: true
        }

        success {
            echo "✅ 恭喜！所有测试用例通过！"
            script { sendEmailNotification('SUCCESS', 'green', '✅') }
        }

        failure {
            echo "❌ 存在失败的测试用例，请查看 Allure 报告。"
            script { sendEmailNotification('FAILURE', 'red', '❌') }
        }
    }
}

// ========== 邮件发送函数 ==========
def sendEmailNotification(String status, String color, String icon) {
    emailext (
        to: env.MAIL_RECIPIENT,
        subject: "${icon} 测试${status == 'SUCCESS' ? '通过' : '失败'} - ${env.JOB_NAME} - Build #${env.BUILD_NUMBER}",
        body: """
            <p>各位同事，大家好！</p>
            <p>项目 <strong>${env.JOB_NAME}</strong> 构建${status == 'SUCCESS' ? '成功' : '失败'}！</p>
            <ul>
                <li>构建编号：<strong>#${env.BUILD_NUMBER}</strong></li>
                <li>构建状态：<span style="color: ${color};">${icon} ${status}</span></li>
                <li>触发人：${env.TRIGGER_USER ?: '未知'}</li>
                <li>测试报告：<a href="${env.REPORT_LINK}">${env.REPORT_LINK}</a></li>
            </ul>
            <p>请点击上方链接查看 Allure 测试报告详情。</p>
            <hr/>
            <p style="font-size: 12px; color: gray;">此邮件由 Jenkins 自动发送，请勿回复。</p>
        """,
        mimeType: 'text/html'
    )
}